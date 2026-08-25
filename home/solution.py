from typing import List, Any


def quicksort(arr: List[Any]) -> List[Any]:
    """Sort a list using the quicksort algorithm."""
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)


def binary_search(arr, target):
    """Perform binary search on a sorted array. Returns index of target, or -1 if not found."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1


def hello():
    """Print a friendly greeting."""
    print("Hello!")


def wassup():
    """Print a casual greeting."""
    print("Wassup!")


if __name__ == "__main__":
    sample = [3, 6, 8, 10, 1, 2, 1]
    print("Sorted:", quicksort(sample))
    sorted_sample = quicksort(sample)
    target = 6
    result = binary_search(sorted_sample, target)
    print(f"Binary search for {target} in {sorted_sample}: index {result}")
    hello()
    wassup()