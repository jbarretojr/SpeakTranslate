import os
import sys
from dotenv import set_key, load_dotenv
from PyQt5.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QMessageBox, QTabWidget, QWidget, QSizePolicy, QSpacerItem, QToolButton, QStyle, QFileDialog
)
from PyQt5.QtCore import Qt, QCoreApplication, QProcess, pyqtSignal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow
from utils import ConfigManager

load_dotenv()

CATEGORY_LABELS = {
    'model_options': 'Opções do modelo',
    'recording_options': 'Opções de gravação',
    'text_transforms': 'Comandos e dicionário',
    'post_processing': 'Pós-processamento',
    'misc': 'Diversos',
}

KEY_LABELS = {
    'use_api': 'Usar API',
    'language': 'Idioma',
    'temperature': 'Temperatura',
    'initial_prompt': 'Prompt inicial',
    'model': 'Modelo',
    'base_url': 'URL base',
    'api_key': 'Chave de API',
    'device': 'Dispositivo',
    'compute_type': 'Tipo de computação',
    'condition_on_previous_text': 'Condicionar ao texto anterior',
    'vad_filter': 'Filtro VAD',
    'model_path': 'Caminho do modelo',
    'activation_key': 'Tecla de ativação',
    'input_backend': 'Backend de entrada',
    'recording_mode': 'Modo de gravação',
    'sound_device': 'Dispositivo de som',
    'sample_rate': 'Taxa de amostragem',
    'silence_duration': 'Duração do silêncio',
    'min_duration': 'Duração mínima',
    'enable_audio_enhancement': 'Aprimorar áudio',
    'highpass_cutoff_hz': 'Passa-alta (Hz)',
    'noise_reduction_strength': 'Redução de ruído',
    'noise_profile_ms': 'Perfil de ruído (ms)',
    'normalize_audio': 'Normalizar volume',
    'writing_key_press_delay': 'Atraso entre teclas',
    'remove_trailing_period': 'Remover ponto final',
    'add_trailing_space': 'Adicionar espaço final',
    'remove_capitalization': 'Remover capitalização',
    'input_method': 'Método de entrada',
    'print_to_terminal': 'Imprimir no terminal',
    'hide_status_window': 'Ocultar janela de status',
    'noise_on_completion': 'Som ao concluir',
    'show_audio_visualizer': 'Equalizador na gravação',
    'enable_voice_commands': 'Ativar comandos de voz',
    'command_prefix': 'Prefixo de comando',
}


class SettingsWindow(BaseWindow):
    settings_closed = pyqtSignal()
    settings_saved = pyqtSignal()
    openTextTransforms = pyqtSignal()

    def __init__(self):
        """Inicializa a janela de configurações."""
        super().__init__('Configurações', 700, 700)
        self.schema = ConfigManager.get_schema()
        self.init_settings_ui()

    def init_settings_ui(self):
        """Inicializa a interface de configurações."""
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self.create_tabs()
        self.create_buttons()

        self.use_api_checkbox = self.findChild(QCheckBox, 'model_options_use_api_input')
        if self.use_api_checkbox:
            self.use_api_checkbox.stateChanged.connect(lambda: self.toggle_api_local_options(self.use_api_checkbox.isChecked()))
            self.toggle_api_local_options(self.use_api_checkbox.isChecked())

    def create_tabs(self):
        """Cria abas para cada categoria do schema."""
        for category, settings in self.schema.items():
            tab = QWidget()
            tab_layout = QVBoxLayout()
            tab.setLayout(tab_layout)
            tab_label = CATEGORY_LABELS.get(category, category.replace('_', ' ').capitalize())
            self.tabs.addTab(tab, tab_label)

            self.create_settings_widgets(tab_layout, category, settings)
            if category == 'text_transforms':
                edit_button = QPushButton('Editar dicionário, comandos e edições automáticas...')
                edit_button.clicked.connect(self.openTextTransforms.emit)
                tab_layout.addWidget(edit_button)
            tab_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

    def create_settings_widgets(self, layout, category, settings):
        """Cria widgets para cada configuração de uma categoria."""
        for sub_category, sub_settings in settings.items():
            if isinstance(sub_settings, dict) and 'value' in sub_settings:
                self.add_setting_widget(layout, sub_category, sub_settings, category)
            else:
                for key, meta in sub_settings.items():
                    self.add_setting_widget(layout, key, meta, category, sub_category)

    def create_buttons(self):
        """Cria os botões de redefinir e salvar."""
        reset_button = QPushButton('Restaurar configurações salvas')
        reset_button.clicked.connect(self.reset_settings)
        self.main_layout.addWidget(reset_button)

        save_button = QPushButton('Salvar')
        save_button.clicked.connect(self.save_settings)
        self.main_layout.addWidget(save_button)

    def _label_for_key(self, key):
        return KEY_LABELS.get(key, key.replace('_', ' ').capitalize())

    def add_setting_widget(self, layout, key, meta, category, sub_category=None):
        """Adiciona um widget de configuração ao layout."""
        item_layout = QHBoxLayout()
        label = QLabel(f"{self._label_for_key(key)}:")
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        widget = self.create_widget_for_type(key, meta, category, sub_category)
        if not widget:
            return

        help_button = self.create_help_button(meta.get('description', ''))

        item_layout.addWidget(label)
        if isinstance(widget, QWidget):
            item_layout.addWidget(widget)
        else:
            item_layout.addLayout(widget)
        item_layout.addWidget(help_button)
        layout.addLayout(item_layout)

        widget_name = f"{category}_{sub_category}_{key}_input" if sub_category else f"{category}_{key}_input"
        label_name = f"{category}_{sub_category}_{key}_label" if sub_category else f"{category}_{key}_label"
        help_name = f"{category}_{sub_category}_{key}_help" if sub_category else f"{category}_{key}_help"
        
        label.setObjectName(label_name)
        help_button.setObjectName(help_name)
        
        if isinstance(widget, QWidget):
            widget.setObjectName(widget_name)
        else:
            line_edit = widget.itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                line_edit.setObjectName(widget_name)

    def create_widget_for_type(self, key, meta, category, sub_category):
        """Cria um widget com base no tipo definido no meta."""
        meta_type = meta.get('type')
        current_value = self.get_config_value(category, sub_category, key, meta)

        if meta_type == 'bool':
            return self.create_checkbox(current_value, key)
        elif meta_type == 'str' and 'options' in meta:
            return self.create_combobox(current_value, meta['options'])
        elif meta_type == 'str':
            return self.create_line_edit(current_value, key)
        elif meta_type in ['int', 'float']:
            return self.create_line_edit(str(current_value))
        elif meta_type == 'list':
            return None
        return None

    def create_checkbox(self, value, key):
        widget = QCheckBox()
        widget.setChecked(value)
        if key == 'use_api':
            widget.setObjectName('model_options_use_api_input')
        return widget

    def create_combobox(self, value, options):
        widget = QComboBox()
        widget.addItems(options)
        widget.setCurrentText(value)
        return widget

    def create_line_edit(self, value, key=None):
        widget = QLineEdit(value)
        if key == 'api_key':
            widget.setEchoMode(QLineEdit.Password)
            widget.setText(os.getenv('OPENAI_API_KEY') or value)
        elif key == 'model_path':
            layout = QHBoxLayout()
            layout.addWidget(widget)
            browse_button = QPushButton('Procurar')
            browse_button.clicked.connect(lambda: self.browse_model_path(widget))
            layout.addWidget(browse_button)
            layout.setContentsMargins(0, 0, 0, 0)
            container = QWidget()
            container.setLayout(layout)
            return container
        return widget

    def create_help_button(self, description):
        help_button = QToolButton()
        help_button.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxQuestion))
        help_button.setAutoRaise(True)
        help_button.setToolTip(description)
        help_button.setCursor(Qt.PointingHandCursor)
        help_button.setFocusPolicy(Qt.TabFocus)
        help_button.clicked.connect(lambda: self.show_description(description))
        return help_button

    def get_config_value(self, category, sub_category, key, meta):
        if sub_category:
            return ConfigManager.get_config_value(category, sub_category, key) or meta['value']
        return ConfigManager.get_config_value(category, key) or meta['value']

    def browse_model_path(self, widget):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Selecionar arquivo do modelo Whisper',
            '',
            'Arquivos de modelo (*.bin);;Todos os arquivos (*)'
        )
        if file_path:
            widget.setText(file_path)

    def show_description(self, description):
        """Exibe um diálogo com a descrição da opção."""
        QMessageBox.information(self, 'Descrição', description)

    def save_settings(self):
        """Salva as configurações no arquivo de config e no .env."""
        self.iterate_settings(self.save_setting)

        api_key = ConfigManager.get_config_value('model_options', 'api', 'api_key') or ''
        set_key('.env', 'OPENAI_API_KEY', api_key)
        os.environ['OPENAI_API_KEY'] = api_key

        ConfigManager.set_config_value(None, 'model_options', 'api', 'api_key')

        ConfigManager.save_config()
        QMessageBox.information(
            self,
            'Configurações salvas',
            'As configurações foram salvas. O aplicativo será reiniciado.'
        )
        self.settings_saved.emit()
        self.close()

    def save_setting(self, widget, category, sub_category, key, meta):
        value = self.get_widget_value_typed(widget, meta.get('type'))
        if sub_category:
            ConfigManager.set_config_value(value, category, sub_category, key)
        else:
            ConfigManager.set_config_value(value, category, key)

    def reset_settings(self):
        """Restaura as configurações para os valores salvos."""
        ConfigManager.reload_config()
        self.update_widgets_from_config()

    def update_widgets_from_config(self):
        """Atualiza todos os widgets com os valores da configuração atual."""
        self.iterate_settings(self.update_widget_value)

    def update_widget_value(self, widget, category, sub_category, key, meta):
        """Atualiza um widget com o valor da configuração."""
        if sub_category:
            config_value = ConfigManager.get_config_value(category, sub_category, key)
        else:
            config_value = ConfigManager.get_config_value(category, key)

        self.set_widget_value(widget, config_value, meta.get('type'))

    def set_widget_value(self, widget, value, value_type):
        """Define o valor de um widget."""
        if isinstance(widget, QCheckBox):
            widget.setChecked(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value) if value is not None else '')
        elif isinstance(widget, QWidget) and widget.layout():
            line_edit = widget.layout().itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                line_edit.setText(str(value) if value is not None else '')

    def get_widget_value_typed(self, widget, value_type):
        """Obtém o valor do widget com o tipo correto."""
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, QComboBox):
            return widget.currentText() or None
        elif isinstance(widget, QLineEdit):
            text = widget.text()
            if value_type == 'int':
                return int(text) if text else None
            elif value_type == 'float':
                return float(text) if text else None
            else:
                return text or None
        elif isinstance(widget, QWidget) and widget.layout():
            line_edit = widget.layout().itemAt(0).widget()
            if isinstance(line_edit, QLineEdit):
                return line_edit.text() or None
        return None

    def toggle_api_local_options(self, use_api):
        """Alterna a visibilidade das opções de API e modelo local."""
        self.iterate_settings(lambda w, c, s, k, m: self.toggle_widget_visibility(w, c, s, k, use_api))

    def toggle_widget_visibility(self, widget, category, sub_category, key, use_api):
        if sub_category in ['api', 'local']:
            widget.setVisible(use_api if sub_category == 'api' else not use_api)
            
            label = self.findChild(QLabel, f"{category}_{sub_category}_{key}_label")
            help_button = self.findChild(QToolButton, f"{category}_{sub_category}_{key}_help")
            
            if label:
                label.setVisible(use_api if sub_category == 'api' else not use_api)
            if help_button:
                help_button.setVisible(use_api if sub_category == 'api' else not use_api)


    def iterate_settings(self, func):
        """Itera sobre todas as configurações e aplica uma função a cada uma."""
        for category, settings in self.schema.items():
            for sub_category, sub_settings in settings.items():
                if isinstance(sub_settings, dict) and 'value' in sub_settings:
                    widget = self.findChild(QWidget, f"{category}_{sub_category}_input")
                    if widget:
                        func(widget, category, None, sub_category, sub_settings)
                else:
                    for key, meta in sub_settings.items():
                        widget = self.findChild(QWidget, f"{category}_{sub_category}_{key}_input")
                        if widget:
                            func(widget, category, sub_category, key, meta)

    def closeEvent(self, event):
        """Confirma antes de fechar a janela de configurações sem salvar."""
        reply = QMessageBox.question(
            self,
            'Fechar sem salvar?',
            'Tem certeza de que deseja fechar sem salvar?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            ConfigManager.reload_config()
            self.update_widgets_from_config()
            self.settings_closed.emit()
            super().closeEvent(event)
        else:
            event.ignore()
