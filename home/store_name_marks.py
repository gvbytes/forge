"""
A simple program to store name and marks in a dictionary.
Provides a menu-driven interface to add students, view data, and calculate averages.
"""

def main():
    # Dictionary to store student names and their marks
    students = {}

    while True:
        print("\n--- Student Marks Menu ---")
        print("1. Add student")
        print("2. View all students")
        print("3. Calculate average marks")
        print("4. Exit")
        choice = input("Enter choice (1-4): ")

        if choice == '1':
            name = input("Enter student name: ")
            try:
                marks = float(input("Enter marks: "))
                students[name] = marks
                print(f"Student '{name}' with marks {marks} added.")
            except ValueError:
                print("Invalid input! Marks must be a number.")

        elif choice == '2':
            if not students:
                print("No students stored yet.")
            else:
                print("\nStored Students:")
                for name, marks in students.items():
                    print(f"  Name: {name} | Marks: {marks}")

        elif choice == '3':
            if not students:
                print("No data available to calculate average.")
            else:
                avg = sum(students.values()) / len(students)
                print(f"\nAverage marks: {avg:.2f}")

        elif choice == '4':
            print("Goodbye!")
            break

        else:
            print("Invalid choice! Please select 1-4.")

if __name__ == "__main__":
    main()