from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_mysqldb import MySQL
from datetime import datetime
from py4j.java_gateway import JavaGateway, GatewayParameters, launch_gateway
import os
from flask_mail import Mail, Message

app = Flask(__name__)

# Configure MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Replace with your MySQL password
app.config['MYSQL_DB'] = 'school_database'  # Ensure this matches your database
mysql = MySQL(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Update as per your email provider
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'palaraoglydel@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'sdks zxhv rjcv mutr'  # Use environment variables for security
app.config['MAIL_DEFAULT_SENDER'] = 'Teacher@gmail.com'

mail = Mail(app)


# Home Page
@app.route('/')
def index():
    cursor = mysql.connection.cursor()

    # Fetch all students and their attendance status
    cursor.execute('''
        SELECT s.student_id, CONCAT(s.first_name, ' ', s.last_name) AS student_name, 
               CASE 
                   WHEN COUNT(a.attendance_id) = 0 THEN 'Absent'
                   WHEN COUNT(a.attendance_id) > 0 THEN 'Present'
               END AS status 
        FROM Students s
        LEFT JOIN Attendance a ON s.student_id = a.student_id
        GROUP BY s.student_id
    ''')
    students = cursor.fetchall()

    # Fetch unique grade levels and sections for filtering
    cursor.execute("SELECT DISTINCT grade_level FROM Students")
    grade_levels = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT section FROM Students")
    sections = [row[0] for row in cursor.fetchall()]

    return render_template('index.html', students=students, grade_levels=grade_levels, sections=sections)

# Add New Student
@app.route('/add_student', methods=['POST'])
def add_student():
    first_name = request.form['first_name']
    last_name = request.form['last_name']
    grade_level = request.form['grade_level']
    section = request.form['section']

    cursor = mysql.connection.cursor()
    cursor.execute('''
        INSERT INTO Students (first_name, last_name, grade_level, section)
        VALUES (%s, %s, %s, %s)
    ''', (first_name, last_name, grade_level, section))
    mysql.connection.commit()

    return redirect(url_for('index'))

@app.route('/filter_students', methods=['GET'])
def filter_students():
    grade_level = request.args.get('grade_level', None)
    section = request.args.get('section', None)

    cursor = mysql.connection.cursor()
    query = '''
        SELECT s.student_id, CONCAT(s.first_name, ' ', s.last_name) AS student_name, 
               s.grade_level, s.section,
               CASE 
                   WHEN COUNT(a.attendance_id) = 0 THEN 'Absent'
                   ELSE 'Present'
               END AS status 
        FROM Students s
        LEFT JOIN Attendance a ON s.student_id = a.student_id
        WHERE (%s IS NULL OR s.grade_level = %s)
          AND (%s IS NULL OR s.section = %s)
        GROUP BY s.student_id
    '''
    cursor.execute(query, (grade_level, grade_level, section, section))
    students = cursor.fetchall()

    # Transform results into JSON-friendly format
    students_data = [
        {
            "id": student[0],
            "name": student[1],
            "grade": student[2],
            "section": student[3],
            "status": student[4]
        } for student in students
    ]
    return jsonify(students_data)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM Students WHERE student_id = %s", (student_id,))
        mysql.connection.commit()

        return jsonify({"message": "Student deleted successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/student/<int:student_id>')
def student_dashboard(student_id):
    cursor = mysql.connection.cursor()

    # Fetch student info
    cursor.execute("SELECT first_name, last_name FROM Students WHERE student_id = %s", (student_id,))
    student = cursor.fetchone()

    if not student:
        return "Student not found.", 404

    # Fetch quizzes from engagement table, including engagement_id
    cursor.execute('''
    SELECT engagement_id, 
        activity_name AS quiz, 
        type As type,  -- Include the type field here
        DATE_FORMAT(date, '%%m/%%d/%%y') AS due_date, 
        CASE WHEN engagement_score >= 75 THEN 'Passed' ELSE 'Failed' END AS status, 
        CONCAT(engagement_score, '%%') AS grade 
    FROM engagement 
    WHERE student_id = %s
''', (student_id,))
    columns = [desc[0] for desc in cursor.description]
    quizzes = [dict(zip(columns, row)) for row in cursor.fetchall()]


    # Debugging output
    print("Quizzes:", quizzes)

    return render_template(
        'student_quizzes.html',
        student={"id": student_id, "name": f"{student[0]} {student[1]}"},
        quizzes=quizzes
    )

@app.route('/delete_quiz/<int:engagement_id>', methods=['POST'])
def delete_quiz(engagement_id):
    try:
        cursor = mysql.connection.cursor()
        
        # Delete the specific quiz using engagement_id
        cursor.execute('''
            DELETE FROM engagement 
            WHERE engagement_id = %s
        ''', (engagement_id,))
        mysql.connection.commit()

        # Check if a row was deleted
        if cursor.rowcount == 0:
            return jsonify({"error": "No quiz found with the given ID."}), 404

        return jsonify({"message": "Quiz deleted successfully!"}), 200
    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/update_quiz_score/<int:student_id>', methods=['POST'])
def update_quiz_score(student_id):
    activity_name = request.form.get('quiz')  # Engagement name
    engagement_score = request.form.get('score')  # Engagement score
    engagement_type = request.form.get('type')  # Engagement type (e.g., Exam, Quiz)

    try:
        cursor = mysql.connection.cursor()

        # Update query to include the type field
        query = '''
            INSERT INTO engagement (student_id, activity_name, type, date, engagement_score)
            VALUES (%s, %s, %s, CURDATE(), %s)
        '''
        cursor.execute(query, (student_id, activity_name, engagement_type, engagement_score))
        mysql.connection.commit()

        # Verify if data was added successfully
        cursor.execute('SELECT * FROM engagement WHERE student_id = %s', (student_id,))
        added_data = cursor.fetchall()

        return jsonify({
            "message": "Engagement score added successfully!",
            "activity_name": activity_name,
            "engagement_type": engagement_type,
            "engagement_score": engagement_score,
            "debug_data": added_data  # Debugging information
        })
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

# Send Suggestion to Student
@app.route('/send_suggestion/<int:student_id>', methods=['POST'])
def send_suggestion(student_id):
    suggestion = request.json.get('suggestion', 'No suggestion provided.')

    # Store feedback in Feedback table
    cursor = mysql.connection.cursor()
    cursor.execute('''
        INSERT INTO Feedback (student_id, feedback_text, recommendations)
        VALUES (%s, %s, %s)
    ''', (student_id, suggestion, "System recommendation"))
    mysql.connection.commit()

    return jsonify({"message": f"Suggestion sent to student {student_id} successfully!"})

@app.route('/student/<int:student_id>/attendance')
def student_attendance(student_id):
    cursor = mysql.connection.cursor()

    # Fetch student info
    cursor.execute("SELECT first_name, last_name FROM Students WHERE student_id = %s", (student_id,))
    student = cursor.fetchone()

    if not student:
        return "Student not found.", 404

    # Fetch attendance records for the student
    cursor.execute('''
        SELECT 
            attendance.attendance_id AS id,
            CONCAT(Students.first_name, ' ', Students.last_name) AS student_name,
            DATE_FORMAT(attendance.date, '%%m/%%d/%%y') AS date,
            attendance.status
        FROM attendance
        JOIN Students ON attendance.student_id = Students.student_id
        WHERE attendance.student_id = %s
    ''', (student_id,))
    columns = [desc[0] for desc in cursor.description]
    attendance_records = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Return the template with the student's attendance data
    return render_template(
        'attendance.html',
        student={"id": student_id, "name": f"{student[0]} {student[1]}"},
        attendance_records=attendance_records
    )


@app.route('/add_attendance/<int:student_id>', methods=['POST'])
def add_attendance(student_id):
    # Retrieve data from the form submission
    date = request.form.get('date')
    status = request.form.get('status')

    if not date or not status:
        return jsonify({"message": "Date and status are required.", "success": False})

    # Insert the new attendance record
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('''
            INSERT INTO attendance (student_id, date, status)
            VALUES (%s, %s, %s)
        ''', (student_id, date, status))
        mysql.connection.commit()
        return jsonify({"message": "Attendance added successfully.", "success": True})
    except Exception as e:
        print("Error adding attendance:", e)
        return jsonify({"message": "Failed to add attendance.", "success": False})
    finally:
        cursor.close()


@app.route('/delete_attendance/<int:attendance_id>', methods=['POST'])
def delete_attendance(attendance_id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM attendance WHERE attendance_id = %s", (attendance_id,))
        mysql.connection.commit()
        return jsonify({"message": "Attendance record deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Initialize Weka Gateway
def initialize_weka():
    try:
        port = launch_gateway(
            classpath="C:/Program Files/Weka-3-8-6/weka.jar",  # Update this to your Weka JAR file path
            die_on_exit=True
        )
        return JavaGateway(
            gateway_parameters=GatewayParameters(port=port)
        )
    except Exception as e:
        print("Error initializing Weka:", str(e))
        return None

gateway = initialize_weka()
if not gateway:
    print("Failed to initialize Weka. Check your Weka JAR path.")


# Initialize Weka Gateway
def initialize_weka():
    try:
        port = launch_gateway(
            classpath="C:/Program Files/Weka-3-8-6/weka.jar",  # Update with your actual path
            die_on_exit=True
        )
        return JavaGateway(
            gateway_parameters=GatewayParameters(port=port)
        )
    except Exception as e:
        print("Error initializing Weka:", str(e))
        return None


gateway = initialize_weka()
if not gateway:
    print("Failed to initialize Weka. Check your Weka JAR path.")


# Analyze Student Performance with Weka
@app.route('/analyze_student/<int:student_id>')
def analyze_student(student_id):
    cursor = mysql.connection.cursor()

    # Fetch engagement, attendance, and grades data
    try:
        cursor.execute('''
            SELECT 
                e.engagement_score AS score, 
                a.status AS attendance, 
                g.score AS grade
            FROM engagement e
            LEFT JOIN attendance a ON e.student_id = a.student_id
            LEFT JOIN grades g ON e.student_id = g.student_id
            WHERE e.student_id = %s
        ''', (student_id,))
        data = cursor.fetchall()

        if not data:
            return jsonify({"error": "No data available for the selected student."}), 404

        # Prepare ARFF data for Weka
        arff_data = "@relation student_performance\n\n"
        arff_data += "@attribute score numeric\n"
        arff_data += "@attribute attendance {Present, Absent, Late}\n"
        arff_data += "@attribute grade {Fail, Pass, Excellent}\n"
        arff_data += "@data\n"

        total_grade = 0
        num_grades = 0

        for row in data:
            grade_category = "Fail" if row[2] < 50 else "Pass" if row[2] <= 70 else "Excellent"
            arff_data += f"{row[0]},{row[1]},{grade_category}\n"

            # Calculate grade total for averaging
            if row[2] is not None:
                total_grade += row[2]
                num_grades += 1

        # Save ARFF data to a file
        arff_file = f"student_{student_id}.arff"
        with open(arff_file, "w") as f:
            f.write(arff_data)

        # Pass ARFF file to Weka
        try:
            jvm = gateway.jvm
            loader = jvm.weka.core.converters.ArffLoader()
            loader.setFile(jvm.java.io.File(arff_file))
            dataset = loader.getDataSet()
            dataset.setClassIndex(dataset.numAttributes() - 1)

            # Use Weka's J48 classifier for analysis
            classifier = jvm.weka.classifiers.trees.J48()
            classifier.buildClassifier(dataset)

            # Calculate averages
            total_engagement = sum([float(dataset.get(i).value(0)) for i in range(dataset.numInstances())])
            total_attendance = sum([1 if dataset.get(i).stringValue(1) == "Present" else 0 for i in range(dataset.numInstances())])
            num_instances = dataset.numInstances()

            avg_engagement = total_engagement / num_instances if num_instances else 0
            avg_attendance = total_attendance / num_instances if num_instances else 0
            avg_combined = (avg_engagement + avg_attendance) / 2

            # Calculate grade average
            avg_grade = total_grade / num_grades if num_grades else 0

            # Suggestion logic
            suggestion = (
                "Good performance overall."
                if num_instances > 0 else
                "Improve attendance, engagement, and grades."
            )

            # Clean up ARFF file after use
            os.remove(arff_file)

            return jsonify({
                "message": "Analysis complete!",
                "suggestion": suggestion,
                "average_engagement": avg_engagement,
                "average_attendance": avg_attendance,
                "average_grade": avg_grade,
                "combined_average": avg_combined
            })

        except Exception as e:
            return jsonify({"error": f"Weka analysis failed: {str(e)}"}), 500

    except Exception as e:
        return jsonify({"error": f"Database query failed: {str(e)}"}), 500

@app.route('/edit_suggestion/<int:student_id>', methods=['POST'])
def edit_suggestion(student_id):
    data = request.get_json()
    new_suggestion = data.get('suggestion')

    if not new_suggestion:
        return jsonify({"error": "Suggestion is required"}), 400

    cursor = mysql.connection.cursor()
    try:
        # Update the suggestion in the database
        cursor.execute(
            "UPDATE suggestions SET suggestion = %s WHERE student_id = %s",
            (new_suggestion, student_id)
        )
        mysql.connection.commit()

        # Retrieve the student's email
        cursor.execute("SELECT email FROM students WHERE student_id = %s", (student_id,))
        student_email = cursor.fetchone()

        if not student_email:
            return jsonify({"error": "Student email not found"}), 404

        # Send the suggestion to the student's email
        msg = Message(
            subject="Updated Suggestion",
            recipients=[student_email[0]],  # Fetch email from the database
            body=f"Dear Student,\n\nYour updated suggestion is:\n\n{new_suggestion}\n\nBest regards,\nYour School"
        )
        mail.send(msg)

        return jsonify({"message": "Suggestion updated and emailed successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route('/student/<int:student_id>/grades')
def student_grades(student_id):
    cursor = mysql.connection.cursor()

    # Fetch student info
    cursor.execute("SELECT first_name, last_name FROM Students WHERE student_id = %s", (student_id,))
    student = cursor.fetchone()

    if not student:
        return "Student not found.", 404

    # Fetch grades from grades table
    cursor.execute('''
    SELECT grade_id,
        subject AS subject,
        grading_period AS grading_period,
        CONCAT(score, '%%') AS score
    FROM grades
    WHERE student_id = %s
    ''', (student_id,))
    
    # Convert query results into a list of dictionaries
    columns = [desc[0] for desc in cursor.description]
    grades = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Debugging output
    print("Grades:", grades)

    return render_template(
        'student_grades.html',
        student={"id": student_id, "name": f"{student[0]} {student[1]}"},
        grades=grades
    )

@app.route('/add_grade/<int:student_id>', methods=['GET', 'POST'])
def add_grade(student_id):
    if request.method == 'POST':
        # Get form data
        subject = request.form['subject']
        score = request.form['score']

        cursor = mysql.connection.cursor()

        # Insert into grades table
        cursor.execute('''
            INSERT INTO grades (student_id, subject, score)
            VALUES (%s, %s, %s)
        ''', (student_id, subject, score))
        mysql.connection.commit()
        cursor.close()

        flash('Grade added successfully!', 'success')
        return redirect(url_for('student_grades', student_id=student_id))

    # GET request: render form
    return render_template('add_grade.html', student_id=student_id)


if __name__ == '__main__':
    app.run(debug=True)
