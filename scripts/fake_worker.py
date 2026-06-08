import sys
import time

def main():
    if len(sys.argv) < 2:
        print("Error: Missing command argument.", file=sys.stderr)
        sys.exit(2)

    command = sys.argv[1]

    if command == "success":
        print("Starting fake success worker...")
        print("Success output.")
        sys.exit(0)
    elif command == "fail":
        print("Starting fake failure worker...")
        print("Encountered error: fake failure command triggered.", file=sys.stderr)
        sys.exit(1)
    elif command == "sleep":
        print("Starting fake sleep worker...")
        sys.stdout.flush()
        print("Sleeping for simulation...")
        sys.stdout.flush()
        try:
            time.sleep(5)
            print("Woke up successfully.")
            sys.exit(0)
        except KeyboardInterrupt:
            print("Sleep interrupted.", file=sys.stderr)
            sys.exit(3)
    else:
        print(f"Error: Unknown command '{command}'.", file=sys.stderr)
        sys.exit(4)

if __name__ == "__main__":
    main()
