from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from py4j.java_gateway import JavaGateway, GatewayParameters, launch_gateway
import os
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash



app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  
app.config['MYSQL_DB'] = 'school_database'  
mysql = MySQL(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'  
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'palaraoglydel@gmail.com' 
app.config['MAIL_PASSWORD'] = 'sdks zxhv rjcv mutr'  
app.config['MAIL_DEFAULT_SENDER'] = 'Teacher@gmail.com'

mail = Mail(app)


@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form data
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Validate form data
        if not first_name or not last_name or not username or not password:
            flash('All fields are required!', 'danger')
            return render_template('register.html')

        # Hash the password
        hashed_password = generate_password_hash(password)

        cursor = mysql.connection.cursor()
        try:
            # Insert new teacher into the database
            cursor.execute('''
                INSERT INTO teachers (first_name, last_name, username, password)
                VALUES (%s, %s, %s, %s)
            ''', (first_name, last_name, username, hashed_password))
            mysql.connection.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error: Unable to register. Username might already exist.', 'danger')
            mysql.connection.rollback()
        finally:
            cursor.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Validate form input
        if not username or not password:
            flash('Please fill out all fields.', 'danger')
            return render_template('login.html')

        cursor = mysql.connection.cursor()
        try:
            # Fetch the user from the database
            cursor.execute("SELECT teacher_id, password FROM teachers WHERE username = %s", (username,))
            user = cursor.fetchone()

            # Check if user exists and password matches
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]  
                flash('Login successful!', 'success')
                return redirect(url_for('index'))  
            else:
                flash('Invalid username or password.', 'danger')
        finally:
            cursor.close()

    return render_template('login.html')

@app.route('/dashboards/<int:student_id>', methods=['GET'])
def dashboards(student_id):
    grading_period = request.args.get('grading_period', default=None)

    try:
        # Fetch student info
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
        student = cur.fetchone()
        if not student:
            return "Student not found", 404

        # Engagement stats with grading period filter
        cur.execute("""
            SELECT type, engagement_score
            FROM engagement
            WHERE student_id = %s
            AND (%s IS NULL OR grading_period = %s)
        """, (student_id, grading_period, grading_period))
        engagement_stats = cur.fetchall()

        # Define a fixed order of types
        fixed_order = ["Quiz", "Recitation", "Exam", "Activity"]
        engagement_data = {etype: [] for etype in fixed_order}

        for engagement_type, score in engagement_stats:
            if engagement_type in engagement_data:
                engagement_data[engagement_type].append(score)

        # Grades stats with grading period filter
        grades_query = """
            SELECT subject, AVG(score) AS average_score
            FROM grades
            WHERE student_id = %s
        """
        grades_params = [student_id]
        if grading_period:
            grades_query += " AND grading_period = %s"
            grades_params.append(grading_period)
        grades_query += " GROUP BY subject"
        cur.execute(grades_query, tuple(grades_params))
        grades = cur.fetchall()

        grades_data = {
            'subjects': [grade[0] for grade in grades],
            'average_scores': [round(grade[1], 2) for grade in grades]
        }

        # Attendance stats with grading period filter
        attendance_query = """
            SELECT status, COUNT(attendance_id) AS count
            FROM attendance
            WHERE student_id = %s
        """
        attendance_params = [student_id]
        if grading_period:
            attendance_query += " AND grading_period = %s"
            attendance_params.append(grading_period)
        attendance_query += " GROUP BY status"
        cur.execute(attendance_query, tuple(attendance_params))
        attendance_stats = cur.fetchall()

        attendance_data = {
            'statuses': [stat[0] for stat in attendance_stats],
            'counts': [stat[1] for stat in attendance_stats]
        }

        cur.close()

        return render_template(
            'dashboard.html',
            student={'id': student[0], 'name': student[1]},  # Adjust column indexes as needed
            engagement_data=engagement_data,
            grades_data=grades_data,
            attendance_data=attendance_data,
            grading_period=grading_period  # Pass grading_period to the template
        )
    except Exception as e:
        return f"An error occurred: {e}", 500


@app.route('/dashboard')
def index():
    # Check if the user is logged in
    if 'user_id' not in session:
        return redirect(url_for('login')) 

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

    cursor.execute("SELECT s.student_id, CONCAT(s.first_name, ' ', s.last_name) AS student_name, s.email FROM Students s")
    student = cursor.fetchone()

    # Fetch unique grade levels and sections for filtering
    cursor.execute("SELECT DISTINCT grade_level FROM Students")
    grade_levels = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT section FROM Students")
    sections = [row[0] for row in cursor.fetchall()]

    return render_template('index.html', students=students, grade_levels=grade_levels, sections=sections, student=student)

@app.route('/logout')
def logout():
    session.pop('user_id', None)  
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# Add New Student
@app.route('/add_student', methods=['POST'])
@app.route('/add_student', methods=['POST'])
def add_student():
    first_name = request.form.get('first_name')
    last_name = request.form.get('last_name')
    grade_level = request.form.get('grade_level')
    section = request.form.get('section')
    email = request.form.get('email')

    # Basic validation
    if not all([first_name, last_name, grade_level, section, email]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    if '@' not in email:
        return jsonify({"success": False, "message": "Invalid email address"}), 400

    try:
        cursor = mysql.connection.cursor()
        cursor.execute('''
            INSERT INTO Students (first_name, last_name, grade_level, section, email)
            VALUES (%s, %s, %s, %s, %s)
        ''', (first_name, last_name, grade_level, section, email))
        mysql.connection.commit()
        cursor.close()
    except Exception as e:
        print(f"Error inserting student: {e}")
        return jsonify({"success": False, "message": "Database error"}), 500

    # Respond with success
    return jsonify({"success": True, "message": "Student added successfully!"})



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

@app.route('/delete_grade/<int:grade_id>', methods=['POST'])
def delete_grade(grade_id):
    try:
        cursor = mysql.connection.cursor()
        
        # Delete the specific grade using grade_id
        cursor.execute('''
            DELETE FROM grades 
            WHERE grade_id = %s
        ''', (grade_id,))
        mysql.connection.commit()

        # Check if a row was deleted
        if cursor.rowcount == 0:
            return jsonify({"error": "No grade found with the given ID."}), 404

        return jsonify({"message": "Grade deleted successfully!"}), 200
    except Exception as e:
        print("Error occurred:", str(e))
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
    activity_name = request.form.get('quiz') 
    engagement_score = request.form.get('score')  
    engagement_type = request.form.get('type')  
    grading_period = request.form.get('grading_period')

    try:
        cursor = mysql.connection.cursor()

        # Update query to include the type field
        query = '''
            INSERT INTO engagement (student_id, activity_name, type, date, engagement_score, grading_period)
            VALUES (%s, %s, %s, CURDATE(), %s, %s)
        '''
        cursor.execute(query, (student_id, activity_name, engagement_type, engagement_score, grading_period))
        mysql.connection.commit()

        # Verify if data was added successfully
        cursor.execute('SELECT * FROM engagement WHERE student_id = %s', (student_id,))
        added_data = cursor.fetchall()

        return jsonify({
           "message": "Engagement score added successfully!",
            "activity_name": activity_name,
            "engagement_type": engagement_type,
            "engagement_score": engagement_score,
            "grading_period": grading_period,
            "debug_data": added_data 
        })
    except Exception as e:
        return jsonify({"message": f"Error: {e}"}), 500

@app.route('/filter_engagements/<student_id>', methods=['GET'])
def filter_engagements(student_id):
    grading_period = request.args.get('grading_period', default=None)

    try:
        # Log input parameters
        app.logger.info("Received student_id: %s, grading_period: %s", student_id, grading_period)

        # Decode and sanitize grading_period
        if grading_period:
            grading_period = grading_period.strip()  
            app.logger.info("Sanitized grading_period: %s", grading_period)

        # Construct SQL query
        query = "SELECT * FROM engagement WHERE student_id = %s"  
        params = [int(student_id)] 

        if grading_period:
            query += " AND grading_period = %s"
            params.append(grading_period)

        # Log the query for debugging
        app.logger.info("Executing query: %s with params: %s", query, params)

        # Execute the query
        cursor = mysql.connection.cursor()
        cursor.execute(query, params)
        engagements = cursor.fetchall()

        # Log query results
        app.logger.info("Query results: %s", engagements)

        # Convert results to JSON
        column_names = [desc[0] for desc in cursor.description]
        engagements_dict = [dict(zip(column_names, row)) for row in engagements]

        return jsonify(engagements_dict)

    except Exception as e:
        # Log the error with full details
        app.logger.error("Error occurred: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/filter_attendance/<int:student_id>', methods=['GET'])
def filter_attendance(student_id):
    grading_period = request.args.get('grading_period', default=None)

    try:
        query = "SELECT * FROM attendance WHERE student_id = %s"
        params = [student_id]

        if grading_period:
            query += " AND grading_period = %s"
            params.append(grading_period)

        cursor = mysql.connection.cursor()
        cursor.execute(query, params)
        attendance_records = cursor.fetchall()

        # Convert query results to JSON
        column_names = [desc[0] for desc in cursor.description]
        attendance_dict = [dict(zip(column_names, row)) for row in attendance_records]

        return jsonify(attendance_dict)

    except Exception as e:
        app.logger.error(f"Error filtering attendance: {e}", exc_info=True)
        return jsonify({"error": "Failed to filter attendance records"}), 500

@app.route('/filter_grades/<int:student_id>', methods=['GET'])
def filter_grades(student_id):
    grading_period = request.args.get('grading_period', default=None)

    try:
        # Base query
        query = "SELECT * FROM grades WHERE student_id = %s"
        params = [student_id]

        # Add grading period condition if provided
        if grading_period:
            query += " AND grading_period = %s"
            params.append(grading_period)

        # Execute query
        cursor = mysql.connection.cursor()
        cursor.execute(query, params)
        grade_records = cursor.fetchall()

        # Convert query results to JSON
        column_names = [desc[0] for desc in cursor.description]
        grade_dict = [dict(zip(column_names, row)) for row in grade_records]

        return jsonify(grade_dict)

    except Exception as e:
        app.logger.error(f"Error filtering grades: {e}", exc_info=True)
        return jsonify({"error": "Failed to filter grade records"}), 500


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
    grading_period = request.form.get('grading_period')  
    # Check if all required fields are provided
    if not date or not status or not grading_period:
        return jsonify({"message": "Date, status, and grading period are required.", "success": False})

    # Insert the new attendance record
    cursor = mysql.connection.cursor()
    try:
        cursor.execute('''
            INSERT INTO attendance (student_id, date, status, grading_period)
            VALUES (%s, %s, %s, %s)
        ''', (student_id, date, status, grading_period))
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
            classpath="C:/Program Files/Weka-3-8-6/weka.jar",  
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
            classpath="C:/Program Files/Weka-3-8-6/weka.jar",  
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


@app.route('/analyze_student/<int:student_id>')
def analyze_student(student_id):
    cursor = mysql.connection.cursor()

    # Get the grading period from query parameters
    grading_period = request.args.get('grading_period', type=int)

    # Validate grading period
    if grading_period not in range(1, 5): 
        return jsonify({"error": "Invalid grading period. Please select a valid period (1-4)."}), 400

    try:
        # Fetch engagement, attendance, and grades data for the selected grading period
        cursor.execute(''' 
            SELECT 
                e.engagement_score AS score, 
                a.status AS attendance, 
                g.score AS grade
            FROM engagement e
            INNER JOIN grades g ON e.student_id = g.student_id AND g.grading_period = %s
            LEFT JOIN attendance a ON e.student_id = a.student_id AND a.grading_period = %s
            WHERE e.student_id = %s AND e.grading_period = %s
        ''', (grading_period, grading_period, student_id, grading_period))
        data = cursor.fetchall()

        if not data:
            return jsonify({"error": "No data available for the selected student and grading period."}), 404

        # Prepare ARFF data for Weka
        arff_data = "@relation student_performance\n\n"
        arff_data += "@attribute score numeric\n"
        arff_data += "@attribute attendance {Present, Absent, Late}\n"
        arff_data += "@attribute grade {Fail, Pass, Excellent}\n"
        arff_data += "@data\n"

        total_grade = 0
        total_engagement = 0
        num_engagements = 0
        num_grades = 0
        total_attendance_score = 0
        num_attendances = 0

        for row in data:
            grade_category = "Fail" if row[2] < 50 else "Pass" if row[2] <= 70 else "Excellent"
            arff_data += f"{row[0]},{row[1]},{grade_category}\n"

            # Calculate totals for averaging
            if row[0] is not None:
                total_engagement += row[0]
                num_engagements += 1

            if row[2] is not None:
                total_grade += row[2]
                num_grades += 1

            # Calculate attendance score
            if row[1] == "Present":
                total_attendance_score += 1
                num_attendances += 1
            elif row[1] == "Late":
                total_attendance_score += 0.5
                num_attendances += 1
            elif row[1] == "Absent":
                num_attendances += 1

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
            avg_engagement = total_engagement / num_engagements if num_engagements else 0
            avg_attendance = total_attendance_score 
            avg_grade = total_grade / num_grades if num_grades else 0
            avg_combined = (avg_engagement + avg_grade) / 2

            # Suggestion logic based on pass/fail status for each average
            suggestion = ""

            if avg_engagement < 50:
                suggestion += "Improve engagement. "
            if avg_attendance < 75:
                suggestion += "Improve attendance. "
            if avg_grade < 50:
                suggestion += "Improve grades. "
            if avg_combined < 60:
                suggestion += "Overall performance needs improvement."

            if not suggestion:  
                suggestion = "Good performance overall."

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



    
@app.route('/send_suggestion/<int:student_id>', methods=['POST'])
def send_suggestion(student_id):
    data = request.json
    suggestion = data.get('suggestion')

    try:
        # Debugging
        print(f"Received student_id: {student_id}")
        print(f"Suggestion: {suggestion}")

        # Fetch student email from the database
        cursor = mysql.connection.cursor()
        query = "SELECT email, first_name FROM students WHERE student_id = %s"
        print(f"Executing query: {query} with student_id={student_id}")
        cursor.execute(query, (student_id,))
        result = cursor.fetchone()

        print(f"Query result: {result}")

        if not result:
            return jsonify({'error': 'Student not found'}), 404

        student_email, student_name = result

        # Compose and send the email
        subject = "Performance Improvement Suggestion"
        body = f"Dear {student_name},\n\nHere is a suggestion to improve your performance:\n\n{suggestion}\n\nBest regards,\nYour Teacher"
        msg = Message(subject, recipients=[student_email])
        msg.body = body
        mail.send(msg)

        return jsonify({'message': 'Suggestion sent successfully!'}), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Failed to send suggestion'}), 500

    finally:
        cursor.close()


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

@app.route('/add_grade/<int:student_id>', methods=['POST'])
def add_grade(student_id):
    if request.method == 'POST':
        # Get form data
        subject = request.form.get('subject')
        score = request.form.get('score')
        grading_period = request.form.get('grading_period')

        # Ensure grading_period is selected
        if not grading_period:
            return jsonify({"success": False, "message": "Grading period is required."})

        cursor = mysql.connection.cursor()

        try:
            # Insert into grades table with grading_period
            cursor.execute(''' 
                INSERT INTO grades (student_id, subject, score, grading_period)
                VALUES (%s, %s, %s, %s)
            ''', (student_id, subject, score, grading_period))
            mysql.connection.commit()
            cursor.close()

            return jsonify({"success": True, "message": "Grade added successfully!"})
        except Exception as e:
            cursor.close()
            return jsonify({"success": False, "message": str(e)})

    return jsonify({"success": False, "message": "Invalid request method."})




if __name__ == '__main__':
    app.run(debug=True)
