def main():
    string = input("Enter a string to check its length: ")
    if not string.strip():
        print("No string entered.")
        return
    print(f"The length of the string is: {len(string)}")

if __name__ == "__main__":
    main()