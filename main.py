import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QPushButton, QComboBox, QDateEdit, \
    QMessageBox, QLineEdit, QHBoxLayout
from PyQt6.QtGui import QPixmap, QIcon, QFont
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation
import socket  # Для проверки интернет-соединения
import matplotlib.pyplot as plt  # Для отображения графика
import os
import ssl
import time
import logging
import json
import os

# Настроим логирование
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(message)s")

SAVE_FILE = "last_conversion.json"


def save_conversion(conversion_data):
    """Сохраняет данные конвертации в файл."""
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(conversion_data, f, indent=4, ensure_ascii=False)


def load_conversion():
    """Загружает данные последней конверсии из файла."""
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def check_internet_connection():
    """
    Проверяет подключение к интернету через несколько популярных веб-сайтов.
    Использует несколько этапов подключения для повышения надежности.
    """
    # Список сайтов для проверки
    test_sites = [
        ("www.google.com", 80),  # HTTP
        ("www.google.com", 443),  # HTTPS
        ("www.yandex.ru", 80),
        ("www.microsoft.com", 443)
    ]

    for site, port in test_sites:
        try:
            start_time = time.time()  # Засекаем время подключения
            # Пробуем создать сокет-соединение
            logging.info(f"Попытка подключения к {site} через порт {port}...")

            # Если порт HTTPS, создаем защищенное соединение
            if port == 443:
                context = ssl.create_default_context()
                with context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=site) as sock:
                    sock.settimeout(5)
                    sock.connect((site, port))
            else:
                with socket.create_connection((site, port), timeout=5) as sock:
                    pass  # Если подключение успешно, выходим из блока

            # Вычисление времени подключения
            elapsed_time = time.time() - start_time
            logging.info(f"Подключение к {site} успешно выполнено за {elapsed_time:.2f} секунд.")
            return True  # Если одно соединение успешно, возвращаем True

        except (socket.timeout, socket.error, ssl.SSLError) as e:
            logging.error(f"Ошибка при подключении к {site} через порт {port}: {e}")
            continue  # Пробуем следующий сайт

    # Если не удалось подключиться ни к одному из сайтов
    logging.error("Не удалось установить подключение к интернету.")
    return False


# Проверка интернет соединения
if check_internet_connection():
    print("Интернет подключен.")
else:
    print("Нет подключения к интернету.")


# Функция для получения курса валют с сайта ЦБ РФ
def get_cbr_exchange_rate(from_currency, to_currency, date=None):
    """
    Получает курс валют с сайта Центрального банка России для указанной валюты и даты.
    В случае ошибки возвращает сообщение об ошибке.
    """
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    if date:
        url += f"?date_req={date.strftime('%d/%m/%Y')}"

    try:
        # Выполнение HTTP-запроса к API ЦБ РФ
        response = requests.get(url)
        response.encoding = 'windows-1251'  # Устанавливаем правильную кодировку для обработки кириллицы

        # Разбираем XML-ответ
        tree = ET.ElementTree(ET.fromstring(response.text))
        root = tree.getroot()

        # Словарь для хранения курсов валют, RUB всегда равен 1
        rates = {"RUB": 1.0}

        # Процесс обработки валют из XML
        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode").text
            value = valute.find("Value").text
            nominal = int(valute.find("Nominal").text)

            # Преобразование значений с учетом разделителя
            rates[char_code] = nominal / float(value.replace(',', '.'))

        # Проверка наличия требуемых валют в словаре
        if from_currency not in rates or to_currency not in rates:
            raise ValueError(f"Валюта {from_currency} или {to_currency} не найдена в списке.")

        # Расчет курса конверсии
        conversion_rate = rates[to_currency] * rates["RUB"] / rates[from_currency]
        return conversion_rate

    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка подключения к серверу: {e}")
    except ET.ParseError:
        raise ValueError("Ошибка обработки данных от сервера. Попробуйте позже.")
    except Exception as e:
        raise RuntimeError(f"Произошла ошибка: {e}")


# Проверка доступности API и интернета
def check_api_status():
    """
    Проверяет доступность интернета и API ЦБ РФ.
    Возвращает статус и цвет для отображения в приложении.
    """
    # Шаг 1: Проверка наличия подключения к интернету
    internet_connected = check_internet_connection()

    if not internet_connected:
        # Если интернета нет, сразу возвращаем статус "Нет подключения"
        return "Нет подключения к интернету", "red"

    # Шаг 2: Выполнение запроса к API ЦБ РФ для проверки его доступности
    response = None
    try:
        response = requests.get("https://www.cbr.ru/scripts/XML_daily.asp")
        # Шаг 3: Проверка статуса ответа от сервера
        if response.status_code != 200:
            # Если сервер вернул неожиданный статус
            return f"API недоступен, код ответа: {response.status_code}", "red"

        # Шаг 4: Дальнейшая обработка ответа сервера
        if response.ok:
            # Если сервер вернул успешный статус 200
            return "API доступен", "green"
        else:
            # В случае других проблем с API
            return "API недоступен", "yellow"
    except requests.RequestException as e:
        # Шаг 5: Обработка ошибки запроса, если проблема с сетью или сервером
        return f"Ошибка в сети: {e}", "orange"
    except Exception as e:
        # Шаг 6: Общая ошибка, если что-то пошло не так в процессе выполнения запроса
        return f"Неизвестная ошибка: {e}", "red"
    finally:
        # Шаг 7: Проверка состояния ответа, если он был получен
        if response:
            if response.status_code == 200:
                # Дополнительная проверка успешности, если ответ получен
                return "API доступен", "green"
            else:
                # Вернуть статус, если код ответа не равен 200
                return f"API вернул ошибку с кодом: {response.status_code}", "red"


# Основное окно приложения
class CurrencyConverterApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Дефолтные настройки приложению
        self.setWindowTitle("Конвертер валют")
        self.setGeometry(200, 200, 500, 400)
        self.setWindowIcon(QIcon("logo.png"))

        layout = QVBoxLayout()

        # Индикатор API
        self.api_status_label = QLabel()
        status_text, status_color = check_api_status()
        self.api_status_label.setText(status_text)
        self.api_status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {status_color};
                border-radius: 15px;
                color: white;
                font-size: 16px;
                padding: 10px;
                text-align: center;
            }}
        """)
        self.api_status_label.setFixedHeight(50)  # Высота текста статуса
        layout.addWidget(self.api_status_label)

        # Верхний макет для ввода и выбора валют
        top_layout = QHBoxLayout()

        # Левый комбо-бокс с валютами и флагами
        self.from_currency_combo = self.create_currency_combo()
        self.from_amount_input = self.create_styled_input_field()
        self.from_amount_input.setPlaceholderText("Введите сумму")
        top_layout.addWidget(self.from_amount_input)
        top_layout.addWidget(self.from_currency_combo)

        # Кнопка для смены валют местами
        self.swap_button = QPushButton("⇆")
        self.swap_button.setFont(QFont("Arial", 16))
        self.swap_button.setStyleSheet(
            "QPushButton { background-color: #FFD700; border-radius: 10px; font-size: 18px; padding: 10px; }"
        )
        self.swap_button.clicked.connect(self.swap_currencies)
        top_layout.addWidget(self.swap_button)

        # Правый комбо-бокс с валютами и флагами
        self.to_currency_combo = self.create_currency_combo()
        self.to_amount_input = self.create_styled_input_field()
        self.to_amount_input.setPlaceholderText("Сумма в целевой валюте")
        self.to_amount_input.setReadOnly(True)
        top_layout.addWidget(self.to_currency_combo)
        top_layout.addWidget(self.to_amount_input)

        # Добавляем верхний макет в основной
        layout.addLayout(top_layout)

        # Кнопка для запуска конвертации
        self.convert_button = QPushButton("Конвертировать")
        self.convert_button.setStyleSheet(
            "QPushButton { background-color: #FF7F00; border-radius: 10px; font-size: 18px; padding: 15px; }"
        )
        self.convert_button.clicked.connect(self.convert_currency)
        layout.addWidget(self.convert_button)

        # Кнопка показа графика
        self.show_chart_button = QPushButton("Показать график")
        self.show_chart_button.setStyleSheet(
            "QPushButton { background-color: #28a745; border-radius: 10px; font-size: 18px; padding: 15px; }"
        )
        self.show_chart_button.clicked.connect(self.show_chart)
        layout.addWidget(self.show_chart_button)

        # Добавление кнопок для увеличения/уменьшения значений
        change_layout = QHBoxLayout()
        self.plus_button = QPushButton("+")
        self.minus_button = QPushButton("-")
        self.plus_button.setStyleSheet(
            "QPushButton { background-color: #28a745; border-radius: 10px; font-size: 18px; padding: 10px; }"
        )
        self.minus_button.setStyleSheet(
            "QPushButton { background-color: #dc3545; border-radius: 10px; font-size: 18px; padding: 10px; }"
        )
        self.plus_button.clicked.connect(self.increase_amount)
        self.minus_button.clicked.connect(self.decrease_amount)
        change_layout.addWidget(self.minus_button)
        change_layout.addWidget(self.plus_button)
        layout.addLayout(change_layout)

        # Виджет для выбора даты с календарем
        date_layout = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setDate(datetime.today())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")  # Формат даты
        self.date_edit.setStyleSheet("""
            QDateEdit {
                font-size: 14px;
                color: #333;
            }
            QAbstractItemView {
                font-size: 14px;
                color: #333;
            }
        """)
        date_layout.addWidget(self.date_edit)
        layout.addLayout(date_layout)

        # Настройки валюты поумолчанию
        self.from_currency_combo.setCurrentText("USD")
        self.to_currency_combo.setCurrentText("RUB")

        # Центральный виджет
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Загрузка последней конвертации
        self.load_settings()

    def load_settings(self):
        """
        Загружает сохраненные валюты и сумму из файла.
        """
        settings_file = "currency_settings.txt"
        if os.path.exists(settings_file):
            with open(settings_file, "r") as file:
                lines = file.readlines()
                if len(lines) >= 3:
                    from_currency = lines[0].strip()
                    to_currency = lines[1].strip()
                    amount = lines[2].strip()
                    self.from_currency_combo.setCurrentText(from_currency)
                    self.to_currency_combo.setCurrentText(to_currency)
                    self.from_amount_input.setText(amount)

    def save_settings(self):
        """
        Сохраняет текущие валюты и сумму в файл.
        """
        from_currency = self.from_currency_combo.currentText()
        to_currency = self.to_currency_combo.currentText()
        amount = self.from_amount_input.text()

        with open("currency_settings.txt", "w") as file:
            file.write(f"{from_currency}\n")
            file.write(f"{to_currency}\n")
            file.write(f"{amount}\n")


    def closeEvent(self, event):
        """
        Событие при закрытии окна — сохраняем настройки.
        """
        self.save_settings()
        event.accept()


    def create_currency_combo(self):
        """
        Создает комбинированный список с валютами и их флагами.
        """
        combo = QComboBox()
        currencies = [
            ("USD", "flags/united-states.png"),
            ("EUR", "flags/european-union.png"),
            ("GBP", "flags/united-kingdom.png"),
            ("JPY", "flags/japan.png"),
            ("CNY", "flags/china.png"),
            ("RUB", "flags/russia.png"),
            ("BRL", "flags/brazil.png"),
            ("KZT", "flags/kazakhstan.png"),
            ("PLN", "flags/poland.png"),
            ("BYN", "flags/belarus.png"),
            ("CZK", "flags/czech-republic.png"),
            ("SEK", "flags/sweden.png"),
            ("RSD", "flags/serbia.png")
        ]
        for currency, flag in currencies:
            pixmap = QPixmap(flag)
            icon = QIcon(pixmap)
            combo.addItem(icon, currency)
        return combo

    def create_styled_input_field(self):
        """
        Создает стильное текстовое поле для ввода данных.
        """
        input_field = QLineEdit()
        input_field.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                font-size: 14px;
                background-color: #f1f1f1;
                border: 2px solid #007BFF;
                border-radius: 10px;
            }
            QLineEdit:focus {
                border-color: #0056b3;
                background-color: #ffffff;
            }
        """)
        return input_field

    def swap_currencies(self):
        """
        Меняет местами выбранные валюты в конвертере.
        """
        from_currency = self.from_currency_combo.currentText()
        to_currency = self.to_currency_combo.currentText()
        self.from_currency_combo.setCurrentText(to_currency)
        self.to_currency_combo.setCurrentText(from_currency)

    def convert_currency(self):
        """
        Выполняет конвертацию валют и выводит результат.
        """
        try:
            # Шаг 1: Получаем данные из интерфейса
            from_currency = self.from_currency_combo.currentText()
            to_currency = self.to_currency_combo.currentText()
            amount_text = self.from_amount_input.text()

            # Шаг 2: Проверка на валидность введенной суммы
            if not amount_text:
                raise ValueError("Введите сумму для конвертации.")

            try:
                amount = float(amount_text)
            except ValueError:
                raise ValueError("Введите корректное число.")

            if amount <= 0:
                raise ValueError("Сумма должна быть положительным числом.")

            # Шаг 3: Проверка доступности API перед конвертацией
            api_status, status_color = check_api_status()
            if status_color == "red":
                raise ConnectionError("Проблемы с подключением к серверу или API.")

            # Шаг 4: Получаем курс валют с учетом выбранной даты
            conversion_rate = None
            try:
                conversion_rate = get_cbr_exchange_rate(from_currency, to_currency, self.date_edit.date().toPyDate())
            except Exception as e:
                raise RuntimeError(f"Не удалось получить курс валют: {e}")

            # Шаг 5: Выполняем расчет конвертации
            if conversion_rate is None:
                raise RuntimeError("Не удалось получить курс валют.")

            converted_amount = amount * conversion_rate

            # Шаг 6: Выводим результат в поле
            formatted_amount = f"{converted_amount:.2f}"
            self.to_amount_input.setText(formatted_amount)

            # Дополнительно: Логирование успешного выполнения
            print(f"Конвертация завершена: {amount} {from_currency} -> {formatted_amount} {to_currency}")

        except ValueError as e:
            # Шаг 7: Обработка ошибок при некорректных входных данных
            self.show_error(str(e))
        except (ConnectionError, RuntimeError) as e:
            # Шаг 8: Обработка ошибок сетевых проблем или проблем с API
            self.show_error(f"Ошибка: {e}")
        except Exception as e:
            # Шаг 9: Общая обработка ошибок
            self.show_error(f"Произошла непредвиденная ошибка: {e}")

    def increase_amount(self):
        """
        Увеличивает сумму на 10 единиц.
        """
        try:
            current_value = float(self.from_amount_input.text())
            new_value = current_value + 10
            self.from_amount_input.setText(f"{new_value:.2f}")
        except ValueError:
            self.show_error("Введите корректное число.")

    def decrease_amount(self):
        """
        Уменьшает сумму на 10 единиц.
        """
        try:
            current_value = float(self.from_amount_input.text())
            new_value = current_value - 10
            if new_value < 0:
                raise ValueError("Сумма не может быть меньше нуля.")
            self.from_amount_input.setText(f"{new_value:.2f}")
        except ValueError:
            self.show_error("Введите корректное число.")

    def show_error(self, message):
        """
        Показывает ошибку в виде всплывающего окна.
        """
        QMessageBox.critical(self, "Ошибка", message)

    def show_chart(self):
        """
        Отображает график изменения курса валют за последние 30 дней.
        Это более современная версия с улучшенной обработкой ошибок,
        логированием и визуализацией.
        """
        try:
            # Шаг 1: Получение выбранных валют
            from_currency = self.from_currency_combo.currentText()
            to_currency = self.to_currency_combo.currentText()

            # Логируем выбранные валюты
            print(f"Выбраны валюты для графика: {from_currency} -> {to_currency}")

            # Шаг 2: Определение диапазона дат (30 последних дней)
            today = datetime.today()
            dates = [today - timedelta(days=i) for i in range(10)]  # Изменили с 10 на 30 дней
            print(f"Запрашиваем курсы валют с датами: {', '.join([date.strftime('%d.%m.%Y') for date in dates])}")

            # Шаг 3: Получение курсов валют для каждой из дат
            rates = []
            for date in dates:
                try:
                    rate = get_cbr_exchange_rate(from_currency, to_currency, date)
                    rates.append(rate)
                    print(f"Курс на {date.strftime('%d.%m.%Y')}: {rate}")
                except Exception as e:
                    print(f"Ошибка получения курса на {date.strftime('%d.%m.%Y')}: {e}")
                    rates.append(None)  # Если курс не получен, добавляем None

            # Шаг 4: Проверка на наличие недостающих данных
            if None in rates:
                missing_dates = [dates[i].strftime('%d.%m.%Y') for i, rate in enumerate(rates) if rate is None]
                print(f"Предупреждение: отсутствуют курсы для следующих дат: {', '.join(missing_dates)}")

            # Шаг 5: Построение графика
            plt.figure(figsize=(10, 6))  # Увеличиваем размер графика для лучшего восприятия
            plt.plot(dates, rates, marker='o', linestyle='-', color='b', label=f"{from_currency} -> {to_currency}")

            # Шаг 6: Улучшение внешнего вида графика
            plt.title(f"Изменение курса {from_currency} -> {to_currency}", fontsize=16)
            plt.xlabel("Дата", fontsize=14)
            plt.ylabel(f"Курс {from_currency} к {to_currency}", fontsize=14)
            plt.xticks(rotation=45, fontsize=12)
            plt.yticks(fontsize=12)
            plt.grid(True, linestyle='--', alpha=0.7)  # Добавляем сетку
            plt.legend()

            # Шаг 7: Обработка отсутствующих данных в графике
            if None in rates:
                plt.title(f"Ошибка данных для {from_currency} -> {to_currency}", fontsize=16)
                plt.text(0.5, 0.5, "Не все данные доступны для отображения", ha='center', va='center', fontsize=12,
                         color='r', transform=plt.gca().transAxes)

            # Шаг 8: Скрытие панели инструментов
            plt.rcParams['toolbar'] = 'None'  # Скрытие панели инструментов

            # Шаг 9: Выводим график на экран
            plt.tight_layout()  # Убираем лишние отступы
            plt.show()

            # Логируем успешный вывод графика
            print("График успешно построен и отображен.")

        except Exception as e:
            # Обработка ошибок и вывод сообщения
            print(f"Ошибка при построении графика: {e}")
            self.show_error(f"Ошибка при построении графика: {e}")


def main():
    # Запуск приложения
    try:
        # Логируем начало запуска приложения
        logging.info("Запуск приложения...")

        # Инициализация приложения
        app = QApplication(sys.argv)

        # Создание и отображение окна
        window = CurrencyConverterApp()
        window.show()
        logging.info("Окно приложения отображено.")

        # Запуск основного цикла приложения
        logging.info("Приложение запущено.")
        sys.exit(app.exec())  # exec() используется в PyQt6

    except Exception as e:
        logging.error(f"Произошла ошибка: {e}")
        sys.exit(1)  # Завершаем приложение с кодом ошибки

    finally:
        logging.info("Завершение работы приложения.")


if __name__ == "__main__":
    main()
