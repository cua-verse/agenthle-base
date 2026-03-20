"""Evaluation helpers for Embedded UART Firmware Design benchmark."""

import re
import logging

logger = logging.getLogger(__name__)


def check_pin_assignments(ioc_text):
    """Check that PA2/PA3 are assigned to USART2 and PA5 is GPIO output.

    Returns dict with:
        'pa2_usart2_tx': bool
        'pa3_usart2_rx': bool
        'pa5_gpio_output': bool
        'all_pass': bool
    """
    results = {
        "pa2_usart2_tx": False,
        "pa3_usart2_rx": False,
        "pa5_gpio_output": False,
        "all_pass": False,
    }

    for line in ioc_text.split('\n'):
        line = line.strip()
        if line == "PA2.Signal=USART2_TX":
            results["pa2_usart2_tx"] = True
        elif line == "PA3.Signal=USART2_RX":
            results["pa3_usart2_rx"] = True
        elif line == "PA5.Signal=GPIO_Output":
            results["pa5_gpio_output"] = True

    results["all_pass"] = all([
        results["pa2_usart2_tx"],
        results["pa3_usart2_rx"],
        results["pa5_gpio_output"],
    ])

    return results


def check_usart2_config(ioc_text, main_c_text):
    """Check USART2 is configured for 115200 baud, 8N1, async mode.

    Checks .ioc for async mode and main.c for init parameters.

    Returns dict with:
        'async_mode': bool
        'baud_115200': bool
        'word_length_8': bool
        'stop_bits_1': bool
        'parity_none': bool
        'all_pass': bool
    """
    results = {
        "async_mode": False,
        "baud_115200": False,
        "word_length_8": False,
        "stop_bits_1": False,
        "parity_none": False,
        "all_pass": False,
    }

    # Check .ioc for async mode
    for line in ioc_text.split('\n'):
        line = line.strip()
        if line == "USART2.VirtualMode=VM_ASYNC":
            results["async_mode"] = True
        elif "PA2.Mode=Asynchronous" in line:
            results["async_mode"] = True

    # Check main.c for USART2 init parameters
    if main_c_text:
        if re.search(r'BaudRate\s*=\s*115200', main_c_text):
            results["baud_115200"] = True
        if "UART_WORDLENGTH_8B" in main_c_text:
            results["word_length_8"] = True
        if "UART_STOPBITS_1" in main_c_text:
            results["stop_bits_1"] = True
        if "UART_PARITY_NONE" in main_c_text:
            results["parity_none"] = True

    results["all_pass"] = all([
        results["async_mode"],
        results["baud_115200"],
        results["word_length_8"],
        results["stop_bits_1"],
        results["parity_none"],
    ])

    return results


def check_timer_frequency(ioc_text, main_c_text, expected_timer_clock=90_000_000):
    """Check that TIM2 prescaler and period produce a 1Hz interrupt.

    TIM2 is on APB1. With SYSCLK=180MHz and APB1 divider=4, APB1 peripheral
    clock=45MHz. Because the divider > 1, timer clock is doubled to 90MHz.
    Valid config: (prescaler+1) * (period+1) = 90,000,000.

    Any factoring is accepted — evaluator checks the product, not specific values.

    Returns dict with:
        'prescaler': int or None
        'period': int or None
        'computed_product': int or None
        'pass': bool
    """
    results = {
        "prescaler": None,
        "period": None,
        "computed_product": None,
        "pass": False,
    }

    prescaler = None
    period = None

    # Try .ioc first
    for line in ioc_text.split('\n'):
        line = line.strip()
        if line.startswith("TIM2.Prescaler="):
            try:
                prescaler = int(line.split('=')[1])
            except ValueError:
                pass
        elif line.startswith("TIM2.Period="):
            try:
                period = int(line.split('=')[1])
            except ValueError:
                pass

    # Fallback to main.c if .ioc didn't have values
    if (prescaler is None or period is None) and main_c_text:
        # Look inside MX_TIM2_Init function
        tim2_match = re.search(
            r'htim2\.Init\.Prescaler\s*=\s*(\d+)', main_c_text
        )
        if tim2_match:
            prescaler = int(tim2_match.group(1))

        period_match = re.search(
            r'htim2\.Init\.Period\s*=\s*(\d+)', main_c_text
        )
        if period_match:
            period = int(period_match.group(1))

    results["prescaler"] = prescaler
    results["period"] = period

    if prescaler is not None and period is not None:
        product = (prescaler + 1) * (period + 1)
        results["computed_product"] = product
        results["pass"] = (product == expected_timer_clock)

    return results


def check_system_clock(ioc_text):
    """Check that system clock is configured to 180MHz.

    Checks .ioc for RCC.SYSCLKFreq_VALUE=180000000 and
    RCC.APB1TimFreq_Value=90000000.

    Returns dict with:
        'sysclk_180mhz': bool
        'apb1_tim_90mhz': bool
        'all_pass': bool
    """
    results = {
        "sysclk_180mhz": False,
        "apb1_tim_90mhz": False,
        "all_pass": False,
    }

    for line in ioc_text.split('\n'):
        line = line.strip()
        if line == "RCC.SYSCLKFreq_VALUE=180000000":
            results["sysclk_180mhz"] = True
        elif line == "RCC.APB1TimFreq_Value=90000000":
            results["apb1_tim_90mhz"] = True

    results["all_pass"] = results["sysclk_180mhz"] and results["apb1_tim_90mhz"]

    return results


def check_nvic_tim2(ioc_text):
    """Check that TIM2 global interrupt is enabled in NVIC.

    The .ioc stores NVIC config as colon-separated fields.
    TIM2_IRQn line starts with 'true' if enabled.

    Returns bool.
    """
    for line in ioc_text.split('\n'):
        line = line.strip()
        if line.startswith("NVIC.TIM2_IRQn="):
            # Format: true\:priority\:subpriority\:...\:preemption\:enabled
            # First field is the enable state
            value = line.split('=', 1)[1]
            return value.startswith("true")
    return False


def check_application_logic(main_c_text):
    """Check that main.c contains correct application logic.

    Verifies:
    - HAL_TIM_Base_Start_IT is called (starts timer interrupt)
    - HAL_TIM_PeriodElapsedCallback is defined
    - Callback checks for TIM2 instance
    - Callback calls HAL_GPIO_TogglePin
    - Callback calls HAL_UART_Transmit

    Returns dict with:
        'timer_start_it': bool
        'callback_defined': bool
        'callback_checks_tim2': bool
        'gpio_toggle': bool
        'uart_transmit': bool
        'all_pass': bool
    """
    results = {
        "timer_start_it": False,
        "callback_defined": False,
        "callback_checks_tim2": False,
        "gpio_toggle": False,
        "uart_transmit": False,
        "hello_message": False,
        "all_pass": False,
    }

    if not main_c_text:
        return results

    # Check HAL_TIM_Base_Start_IT is called
    if re.search(r'HAL_TIM_Base_Start_IT\s*\(\s*&htim2\s*\)', main_c_text):
        results["timer_start_it"] = True

    # Check callback is defined
    callback_match = re.search(
        r'void\s+HAL_TIM_PeriodElapsedCallback\s*\(\s*TIM_HandleTypeDef\s*\*\s*\w+\s*\)',
        main_c_text
    )
    if callback_match:
        results["callback_defined"] = True

        # Extract callback body (use larger window to handle formatting differences)
        callback_start = callback_match.start()
        callback_region = main_c_text[callback_start:callback_start + 3000]

        # Check for proper TIM2 instance check (not just substring)
        if re.search(r'Instance\s*==\s*TIM2', callback_region):
            results["callback_checks_tim2"] = True
        if "HAL_GPIO_TogglePin" in callback_region:
            results["gpio_toggle"] = True
        if "HAL_UART_Transmit" in callback_region:
            results["uart_transmit"] = True
        # Verify the transmitted string is "Hello\r\n"
        if re.search(r'["\']Hello\\r\\n["\']', callback_region):
            results["hello_message"] = True

    results["all_pass"] = all([
        results["timer_start_it"],
        results["callback_defined"],
        results["callback_checks_tim2"],
        results["gpio_toggle"],
        results["uart_transmit"],
        results["hello_message"],
    ])

    return results