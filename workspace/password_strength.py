def check_password_strength(password):
    strength = "Weak"
    score = 0

    if len(password) >= 8:
        score += 1
    if any(c.isupper() for c in password):
        score += 1
    if any(c.islower() for c in password):
        score += 1
    if any(c.isdigit() for c in password):
        score += 1
    if any(not c.isalnum() for c in password):
        score += 1

    if score <= 1:
        strength = "Weak"
    elif score == 2:
        strength = "Moderate"
    elif score == 3:
        strength = "Strong"
    else:
        strength = "Very Strong"

    return strength


def main():
    password = input("Enter a password to check its strength: ").strip()
    if not password:
        print("No password entered.")
        return
    result = check_password_strength(password)
    print(f"Password strength: {result}")


if __name__ == "__main__":
    main()