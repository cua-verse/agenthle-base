"""Embedded UART Firmware Design Task - Hardware Design Benchmark."""

import os
import logging
from dataclasses import dataclass

import cua_bench as cb
from tasks.common_config import GeneralTaskConfig
from tasks.hardware.Embedded_UART.eval import (
    check_pin_assignments,
    check_usart2_config,
    check_timer_frequency,
    check_system_clock,
    check_nvic_tim2,
    check_application_logic,
)

logger = logging.getLogger(__name__)


def _cmd_stdout(result):
    """Extract stdout string from run_command result (may be dict or str)."""
    if isinstance(result, dict):
        return result.get("stdout", "")
    return result or ""


@dataclass
class TaskConfig(GeneralTaskConfig):
    TASK_TAG: str = "Embedded_UART"
    TASK_CATEGORY: str = "hardware"
    OS_TYPE: str = "windows"

    # Design spec
    TARGET_MCU: str = "STM32F446RET6"
    SYSCLK_HZ: int = 180_000_000
    APB1_TIM_CLK_HZ: int = 90_000_000
    UART_BAUD: int = 115200
    TIMER_FREQ_HZ: int = 1

    # Pin assignments
    USART2_TX_PIN: str = "PA2"
    USART2_RX_PIN: str = "PA3"
    LED_PIN: str = "PA5"

    # Tool paths on the VM
    CUBEMX_PATH: str = os.environ.get(
        "CUBEMX_PATH", "C:\\Program Files\\STMicroelectronics\\STM32CubeMX\\STM32CubeMX.exe"
    )
    CUBEIDE_PATH: str = os.environ.get(
        "CUBEIDE_PATH", "C:\\ST\\STM32CubeIDE_2.1.1\\STM32CubeIDE\\stm32cubeide.exe"
    )

    # Project structure
    PROJECT_NAME: str = "uart_firmware"
    IOC_FILE: str = "uart_firmware.ioc"
    MAIN_C_PATH: str = "Core\\Src\\main.c"
    ELF_PATH: str = "Debug\\uart_firmware.elf"

    # Input files
    DATASHEET_FILE: str = "STM32F446RE_datasheet.pdf"

    @property
    def task_dir(self):
        return f"{self.REMOTE_ROOT_DIR}\\{self.TASK_CATEGORY}\\{self.TASK_TAG}"

    @property
    def task_description(self):
        return f"""Configure an STM32F446RE microcontroller and implement a UART-based firmware application.

        Existing File Structure:
        {self.task_dir}\\
        ├── input\\
        │   └── {self.DATASHEET_FILE}         # MCU datasheet (reference material)
        └── output\\
            └── {self.PROJECT_NAME}\\
                └── {self.IOC_FILE}            # Blank CubeMX project (open in CubeMX)

        Design Requirements:
        - MCU: {self.TARGET_MCU}
        - System clock: 180MHz
        - USART2: {self.USART2_TX_PIN} (TX), {self.USART2_RX_PIN} (RX), {self.UART_BAUD} baud, 8N1
        - Timer interrupt at {self.TIMER_FREQ_HZ}Hz
        - LED on {self.LED_PIN}: toggle every timer tick
        - On each timer tick, transmit "Hello\\r\\n" over UART
        - Final deliverable: compiled .elf binary with 0 build errors

        Environment:
        - STM32CubeMX is open with {self.IOC_FILE} loaded, showing {self.TARGET_MCU}
        - STM32CubeIDE is installed on the system
        - The project name and output location are pre-configured in the .ioc file — do not change them
        - Use CubeMX to configure peripherals and generate initialization code, then use CubeIDE to write application logic in main.c and build the project
        - After you generate code in CubeMX, click "Open Project" to open the project in STM32CubeIDE

        Do not ask for confirmation. Execute each step directly.
        """

    def to_metadata(self):
        metadata = super().to_metadata()
        metadata.update({
            "target_mcu": self.TARGET_MCU,
            "sysclk_hz": self.SYSCLK_HZ,
            "apb1_tim_clk_hz": self.APB1_TIM_CLK_HZ,
            "uart_baud": self.UART_BAUD,
            "timer_freq_hz": self.TIMER_FREQ_HZ,
        })
        return metadata


config = TaskConfig()


@cb.tasks_config(split="train")
def load():
    return [
        cb.Task(
            description=config.task_description,
            metadata=config.to_metadata(),
            computer={
                "provider": "computer",
                "setup_config": {
                    "os_type": config.OS_TYPE,
                }
            },
        )
    ]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    logger.info(f"Setting up task: {config.TASK_TAG}")
 
    try:
        output_dir = task_cfg.metadata["remote_output_dir"]
        input_dir = os.path.join(os.path.dirname(output_dir), "input")
 
        # Clean and create output directory
        await session.remove_file(output_dir)
        await session.makedirs(output_dir)
 
        # Copy uart_firmware project folder from input to output
        src_project = os.path.join(input_dir, config.PROJECT_NAME)
        dst_project = os.path.join(output_dir, config.PROJECT_NAME)
        await session.run_command(
            f'powershell -Command "Copy-Item -Path \'{src_project}\' -Destination \'{dst_project}\' -Recurse"'
        )
 
        # Open .ioc in CubeMX
        ioc_path = os.path.join(dst_project, config.IOC_FILE)
        await session.run_command(
            f'powershell -Command "Start-Process \'{ioc_path}\' -WindowStyle Maximized"'
        )
 
    except Exception as e:
        logger.warning(f"Failed to setup task {config.TASK_TAG}: {e}")
 
 
# ── Evaluation ──
 
@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession) -> list[float]:
    """Score the task: peripheral config checks + build + application logic."""
 
    output_dir = task_cfg.metadata["remote_output_dir"]
    project_dir = os.path.join(output_dir, config.PROJECT_NAME)
    score = 0.0
 
    # ── Read .ioc file ──
    ioc_text = None
    try:
        ioc_path = os.path.join(project_dir, config.IOC_FILE)
        ioc_bytes = await session.read_bytes(ioc_path)
        if ioc_bytes:
            ioc_text = ioc_bytes.decode('utf-8', errors='replace')
    except Exception:
        pass
 
    if not ioc_text:
        logger.info("Could not read .ioc file — all config checkpoints will fail")
 
    # ── Read main.c ──
    main_c_text = None
    try:
        main_c_path = os.path.join(project_dir, config.MAIN_C_PATH)
        main_c_bytes = await session.read_bytes(main_c_path)
        if main_c_bytes:
            main_c_text = main_c_bytes.decode('utf-8', errors='replace')
    except Exception:
        pass
 
    # ══════════════════════════════════════════════
    # Checkpoint 0: Pin Assignments (0.10)
    # PA2 → USART2_TX, PA3 → USART2_RX, PA5 → GPIO_Output
    # ══════════════════════════════════════════════
    if ioc_text:
        pin_results = check_pin_assignments(ioc_text)
        if pin_results["all_pass"]:
            score += 0.10
            logger.info("Checkpoint 0 PASSED: Pin assignments correct")
        else:
            logger.info(f"Checkpoint 0 FAILED: Pin assignments — "
                        f"PA2_TX={pin_results['pa2_usart2_tx']}, "
                        f"PA3_RX={pin_results['pa3_usart2_rx']}, "
                        f"PA5_GPIO={pin_results['pa5_gpio_output']}")
    else:
        logger.info("Checkpoint 0 FAILED: .ioc file not found")
 
    # ══════════════════════════════════════════════
    # Checkpoint 1: USART2 Configuration (0.15)
    # 115200 baud, 8-bit, no parity, 1 stop bit, async
    # ══════════════════════════════════════════════
    if ioc_text:
        usart_results = check_usart2_config(ioc_text, main_c_text)
        if usart_results["all_pass"]:
            score += 0.15
            logger.info("Checkpoint 1 PASSED: USART2 configured 115200/8N1/async")
        else:
            logger.info(f"Checkpoint 1 FAILED: USART2 config — "
                        f"async={usart_results['async_mode']}, "
                        f"baud={usart_results['baud_115200']}, "
                        f"word={usart_results['word_length_8']}, "
                        f"stop={usart_results['stop_bits_1']}, "
                        f"parity={usart_results['parity_none']}")
    else:
        logger.info("Checkpoint 1 FAILED: .ioc file not found")
 
    # ══════════════════════════════════════════════
    # Checkpoint 2: Timer Frequency (0.15)
    # (prescaler+1) * (period+1) = 90,000,000 for 1Hz
    # ══════════════════════════════════════════════
    if ioc_text:
        timer_results = check_timer_frequency(
            ioc_text, main_c_text,
            expected_timer_clock=config.APB1_TIM_CLK_HZ
        )
        if timer_results["pass"]:
            score += 0.15
            logger.info(f"Checkpoint 2 PASSED: Timer frequency 1Hz "
                        f"(prescaler={timer_results['prescaler']}, "
                        f"period={timer_results['period']}, "
                        f"product={timer_results['computed_product']})")
        else:
            logger.info(f"Checkpoint 2 FAILED: Timer frequency — "
                        f"prescaler={timer_results['prescaler']}, "
                        f"period={timer_results['period']}, "
                        f"product={timer_results['computed_product']} "
                        f"(expected {config.APB1_TIM_CLK_HZ})")
    else:
        logger.info("Checkpoint 2 FAILED: .ioc file not found")
 
    # ══════════════════════════════════════════════
    # Checkpoint 3: System Clock (0.10)
    # SYSCLK = 180MHz, APB1 timer clock = 90MHz
    # ══════════════════════════════════════════════
    if ioc_text:
        clock_results = check_system_clock(ioc_text)
        if clock_results["all_pass"]:
            score += 0.10
            logger.info("Checkpoint 3 PASSED: SYSCLK=180MHz, APB1_TIM=90MHz")
        else:
            logger.info(f"Checkpoint 3 FAILED: Clock config — "
                        f"sysclk_180={clock_results['sysclk_180mhz']}, "
                        f"apb1_tim_90={clock_results['apb1_tim_90mhz']}")
    else:
        logger.info("Checkpoint 3 FAILED: .ioc file not found")
 
    # ══════════════════════════════════════════════
    # Checkpoint 4: TIM2 NVIC Interrupt Enabled (0.10)
    # ══════════════════════════════════════════════
    if ioc_text:
        if check_nvic_tim2(ioc_text):
            score += 0.10
            logger.info("Checkpoint 4 PASSED: TIM2 NVIC interrupt enabled")
        else:
            logger.info("Checkpoint 4 FAILED: TIM2 NVIC interrupt not enabled")
    else:
        logger.info("Checkpoint 4 FAILED: .ioc file not found")
 
    # ══════════════════════════════════════════════
    # Checkpoint 5: Build Success (0.20)
    # .elf file exists with reasonable size
    # ══════════════════════════════════════════════
    elf_exists = False
    try:
        elf_path = os.path.join(project_dir, config.ELF_PATH)
        elf_check = await session.run_command(
            f'powershell -Command "if (Test-Path \'{elf_path}\') '
            f'{{ (Get-Item \'{elf_path}\').Length }} else {{ 0 }}"'
        )
        elf_size = int(_cmd_stdout(elf_check).strip()) if _cmd_stdout(elf_check).strip().isdigit() else 0
        if elf_size > 1000:
            elf_exists = True
            score += 0.20
            logger.info(f"Checkpoint 5 PASSED: .elf produced ({elf_size} bytes)")
        else:
            logger.info(f"Checkpoint 5 FAILED: .elf not found or too small ({elf_size} bytes)")
    except Exception as e:
        logger.info(f"Checkpoint 5 FAILED: {e}")
 
    # ══════════════════════════════════════════════
    # Checkpoint 6: Application Logic (0.20)
    # Timer callback with UART transmit and GPIO toggle
    # ══════════════════════════════════════════════
    if main_c_text:
        logic_results = check_application_logic(main_c_text)
        if logic_results["all_pass"]:
            score += 0.20
            logger.info("Checkpoint 6 PASSED: Application logic correct")
        else:
            logger.info(f"Checkpoint 6 FAILED: Application logic — "
                        f"timer_start={logic_results['timer_start_it']}, "
                        f"callback={logic_results['callback_defined']}, "
                        f"tim2_check={logic_results['callback_checks_tim2']}, "
                        f"gpio_toggle={logic_results['gpio_toggle']}, "
                        f"uart_transmit={logic_results['uart_transmit']}, "
                        f"hello_msg={logic_results['hello_message']}")
    else:
        logger.info("Checkpoint 6 FAILED: main.c not found")
 
    logger.info(f"Final score: {score:.2f}")
    return [score]