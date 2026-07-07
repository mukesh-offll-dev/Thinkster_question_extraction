import sys
sys.path.append(".")

from add_worksheets import run_addition

student_url = "https://tutor4.0.hellothinkster.com/students/626b0368-19b9-4c31-843d-7113872324b9"
subject = "Algebra 2"
worksheet_ids = ["AQMODRAL201"]
email = "intern@hellothinkster.com"
password = "Password"

run_addition(student_url, subject, worksheet_ids, email, password)
