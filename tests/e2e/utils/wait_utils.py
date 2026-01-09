import time
from typing import Callable, Any, Optional


def wait_for(
    condition: Callable[[], bool],
    timeout: int = 30,
    interval: float = 1.0,
    error_message: Optional[str] = None
) -> bool:
    """
    Wait for a condition to become true within a timeout period.

    Args:
        condition: Callable that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between condition checks in seconds
        error_message: Custom error message if timeout occurs

    Returns:
        True if condition was met, False if timeout occurred

    Raises:
        TimeoutError: If condition not met within timeout and error_message provided
    """
    start_time = time.time()
    last_exception = None

    while time.time() - start_time < timeout:
        try:
            if condition():
                return True
        except Exception as e:
            last_exception = e

        time.sleep(interval)

    if error_message:
        if last_exception:
            raise TimeoutError(f"{error_message}. Last exception: {last_exception}")
        raise TimeoutError(error_message)

    return False


def wait_for_value(
    getter: Callable[[], Any],
    expected_value: Any = None,
    validator: Optional[Callable[[Any], bool]] = None,
    timeout: int = 30,
    interval: float = 1.0,
    error_message: Optional[str] = None
) -> Any:
    """
    Wait for a getter function to return an expected value or pass validation.

    Args:
        getter: Callable that returns a value to check
        expected_value: Expected value (if validator not provided)
        validator: Callable that validates the returned value
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        error_message: Custom error message if timeout occurs

    Returns:
        The value that satisfied the condition

    Raises:
        TimeoutError: If condition not met within timeout
    """
    start_time = time.time()
    last_value = None
    last_exception = None

    while time.time() - start_time < timeout:
        try:
            value = getter()
            last_value = value

            if validator:
                if validator(value):
                    return value
            elif value == expected_value:
                return value

        except Exception as e:
            last_exception = e

        time.sleep(interval)

    msg = error_message or f"Timeout waiting for expected value. Last value: {last_value}"
    if last_exception:
        msg += f". Last exception: {last_exception}"

    raise TimeoutError(msg)
