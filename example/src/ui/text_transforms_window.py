import os
import sys

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QWidget, QTableWidget, QTableWidgetItem, QCheckBox, QComboBox, QMessageBox,
    QHeaderView, QAbstractItemView,
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow
from text_processing import BUILTIN_VOICE_COMMANDS
from utils import ConfigManager


KEY_ACTION_OPTIONS = sorted(set(BUILTIN_VOICE_COMMANDS.values()) | {
    'ctrl+a', 'ctrl+s', 'ctrl+x', 'ctrl+shift+v',
})


class TextTransformsWindow(BaseWindow):
    saved = pyqtSignal()

    def __init__(self):
        super().__init__('Comandos de voz e dicionário', 720, 560)
        self.init_ui()
        self.load_from_config()

    def init_ui(self):
        intro = QLabel(
            'Configure substituições de texto e comandos de voz. '
            'Para executar uma tecla, diga apenas o prefixo seguido do comando '
            '(ex.: "comando enter", "comando nova linha", "comando copiar").'
        )
        intro.setWordWrap(True)
        intro.setStyleSheet('color: #505050; padding: 4px 0;')
        self.main_layout.addWidget(intro)

        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self.commands_table = self._create_commands_tab()
        self.dictionary_table = self._create_dictionary_tab()
        self.edits_table = self._create_edits_tab()

        options_row = QHBoxLayout()
        self.enable_commands_checkbox = QCheckBox('Ativar comandos de voz')
        self.enable_commands_checkbox.setChecked(True)
        options_row.addWidget(self.enable_commands_checkbox)

        prefix_label = QLabel('Prefixo:')
        self.prefix_edit = QComboBox()
        self.prefix_edit.setEditable(True)
        self.prefix_edit.addItems(['comando', 'cmd'])
        options_row.addWidget(prefix_label)
        options_row.addWidget(self.prefix_edit)
        options_row.addStretch(1)
        self.main_layout.addLayout(options_row)

        buttons = QHBoxLayout()
        save_button = QPushButton('Salvar')
        save_button.clicked.connect(self.save)
        cancel_button = QPushButton('Cancelar')
        cancel_button.clicked.connect(self.close)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        self.main_layout.addLayout(buttons)

    def _setup_table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        return table

    def _create_commands_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        builtin_label = QLabel(
            'Comandos integrados: ' +
            ', '.join(f'"{name}"' for name in sorted(BUILTIN_VOICE_COMMANDS.keys()))
        )
        builtin_label.setWordWrap(True)
        builtin_label.setStyleSheet('color: #606060; font-size: 11px;')
        layout.addWidget(builtin_label)

        table = self._setup_table(['Gatilho (após o prefixo)', 'Ação de tecla'])
        layout.addWidget(table)

        row_buttons = QHBoxLayout()
        add_button = QPushButton('Adicionar')
        add_button.clicked.connect(lambda: self._add_command_row())
        remove_button = QPushButton('Remover selecionado')
        remove_button.clicked.connect(lambda: self._remove_selected(table))
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)
        layout.addLayout(row_buttons)

        self.tabs.addTab(tab, 'Comandos de voz')
        return table

    def _create_dictionary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel('Coluna esquerda: o que o Whisper transcreve. Coluna direita: o texto final.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #606060; font-size: 11px;')
        layout.addWidget(hint)

        table = self._setup_table(['Whisper escreve', 'Substituir por'])
        layout.addWidget(table)

        row_buttons = QHBoxLayout()
        add_button = QPushButton('Adicionar')
        add_button.clicked.connect(lambda: self._add_dictionary_row())
        remove_button = QPushButton('Remover selecionado')
        remove_button.clicked.connect(lambda: self._remove_selected(table))
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)
        layout.addLayout(row_buttons)

        self.tabs.addTab(tab, 'Dicionário pessoal')
        return table

    def _create_edits_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel('Regras aplicadas em ordem após o dicionário. Marque Regex para padrões avançados.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #606060; font-size: 11px;')
        layout.addWidget(hint)

        table = self._setup_table(['Localizar', 'Substituir por', 'Regex'])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(table)

        row_buttons = QHBoxLayout()
        add_button = QPushButton('Adicionar')
        add_button.clicked.connect(lambda: self._add_edit_row())
        remove_button = QPushButton('Remover selecionado')
        remove_button.clicked.connect(lambda: self._remove_selected(table))
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)
        layout.addLayout(row_buttons)

        self.tabs.addTab(tab, 'Edições automáticas')
        return table

    def _add_command_row(self, trigger='', action='enter'):
        row = self.commands_table.rowCount()
        self.commands_table.insertRow(row)
        self.commands_table.setItem(row, 0, QTableWidgetItem(trigger))

        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(KEY_ACTION_OPTIONS)
        combo.setCurrentText(action)
        self.commands_table.setCellWidget(row, 1, combo)

    def _add_dictionary_row(self, find_text='', replace_text=''):
        row = self.dictionary_table.rowCount()
        self.dictionary_table.insertRow(row)
        self.dictionary_table.setItem(row, 0, QTableWidgetItem(find_text))
        self.dictionary_table.setItem(row, 1, QTableWidgetItem(replace_text))

    def _add_edit_row(self, find_text='', replace_text='', use_regex=False):
        row = self.edits_table.rowCount()
        self.edits_table.insertRow(row)
        self.edits_table.setItem(row, 0, QTableWidgetItem(find_text))
        self.edits_table.setItem(row, 1, QTableWidgetItem(replace_text))

        checkbox = QCheckBox()
        checkbox.setChecked(use_regex)
        checkbox.setStyleSheet('margin-left: 12px;')
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.addWidget(checkbox)
        wrapper_layout.setAlignment(Qt.AlignCenter)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.edits_table.setCellWidget(row, 2, wrapper)

    def _remove_selected(self, table):
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    def load_from_config(self):
        transforms = ConfigManager.get_config_section('text_transforms')

        self.enable_commands_checkbox.setChecked(
            transforms.get('enable_voice_commands', True)
        )
        prefix = transforms.get('command_prefix') or 'comando'
        self.prefix_edit.setCurrentText(prefix)

        self.commands_table.setRowCount(0)
        for entry in transforms.get('custom_voice_commands') or []:
            self._add_command_row(
                str(entry.get('trigger', '')),
                str(entry.get('action', 'enter')),
            )

        self.dictionary_table.setRowCount(0)
        for entry in transforms.get('personal_dictionary') or []:
            self._add_dictionary_row(
                str(entry.get('find', '')),
                str(entry.get('replace', '')),
            )

        self.edits_table.setRowCount(0)
        for entry in transforms.get('auto_edits') or []:
            self._add_edit_row(
                str(entry.get('find', '')),
                str(entry.get('replace', '')),
                bool(entry.get('regex', False)),
            )

    def _read_commands(self):
        commands = []
        for row in range(self.commands_table.rowCount()):
            trigger_item = self.commands_table.item(row, 0)
            action_widget = self.commands_table.cellWidget(row, 1)
            trigger = trigger_item.text().strip() if trigger_item else ''
            action = action_widget.currentText().strip() if action_widget else ''
            if trigger and action:
                commands.append({'trigger': trigger, 'action': action})
        return commands

    def _read_dictionary(self):
        entries = []
        for row in range(self.dictionary_table.rowCount()):
            find_item = self.dictionary_table.item(row, 0)
            replace_item = self.dictionary_table.item(row, 1)
            find_text = find_item.text().strip() if find_item else ''
            replace_text = replace_item.text().strip() if replace_item else ''
            if find_text:
                entries.append({'find': find_text, 'replace': replace_text})
        return entries

    def _read_edits(self):
        rules = []
        for row in range(self.edits_table.rowCount()):
            find_item = self.edits_table.item(row, 0)
            replace_item = self.edits_table.item(row, 1)
            checkbox_widget = self.edits_table.cellWidget(row, 2)
            checkbox = checkbox_widget.findChild(QCheckBox) if checkbox_widget else None
            find_text = find_item.text().strip() if find_item else ''
            replace_text = replace_item.text().strip() if replace_item else ''
            if find_text:
                rules.append({
                    'find': find_text,
                    'replace': replace_text,
                    'regex': checkbox.isChecked() if checkbox else False,
                })
        return rules

    def save(self):
        ConfigManager.set_config_value(
            self.enable_commands_checkbox.isChecked(),
            'text_transforms', 'enable_voice_commands',
        )
        ConfigManager.set_config_value(
            self.prefix_edit.currentText().strip() or 'comando',
            'text_transforms', 'command_prefix',
        )
        ConfigManager.set_config_value(
            self._read_commands(),
            'text_transforms', 'custom_voice_commands',
        )
        ConfigManager.set_config_value(
            self._read_dictionary(),
            'text_transforms', 'personal_dictionary',
        )
        ConfigManager.set_config_value(
            self._read_edits(),
            'text_transforms', 'auto_edits',
        )
        ConfigManager.save_config()
        self.saved.emit()
        QMessageBox.information(self, 'Salvo', 'Comandos e dicionário salvos.')
        self.close()


if __name__ == '__main__':
    ConfigManager.initialize()
    app = QApplication(sys.argv)
    window = TextTransformsWindow()
    window.show()
    sys.exit(app.exec_())
