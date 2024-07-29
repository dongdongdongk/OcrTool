import sys
import cv2
import numpy as np
from google.cloud import vision
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QLineEdit, QScrollArea
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPixmap, QMouseEvent, QCursor

class TransparentOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 위젯을 투명하게 만들고 프레임 없이 항상 최상위에 표시
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.dragging = False
        self.resizing = False
        self.resize_edge = None
        self.offset = QPoint()
        self.border_thickness = 5
        self.header_height = 30

        # 레이아웃 설정
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 헤더 위젯 생성 및 스타일 설정
        self.header = QWidget(self)
        self.header.setFixedHeight(self.header_height)
        self.header.setStyleSheet("background-color: rgba(255, 0, 0, 128);")
        self.layout.addWidget(self.header)
        self.layout.addStretch()

    def paintEvent(self, event):
        # 빨간색 테두리 그리기
        painter = QPainter(self)
        painter.setPen(QColor(255, 0, 0))
        for i in range(self.border_thickness):
            painter.drawRect(i, i, self.width() - 1 - 2*i, self.height() - 1 - 2*i)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.header.geometry().contains(event.position().toPoint()):
                # 헤더를 클릭하면 드래그 시작
                self.dragging = True
                self.offset = event.position().toPoint()
            else:
                # 테두리를 클릭하면 리사이징 시작
                edge = self.get_resize_edge(event.position().toPoint())
                if edge:
                    self.resizing = True
                    self.resize_edge = edge

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging:
            # 드래그 중이면 위젯 이동
            new_pos = QCursor.pos() - self.offset
            self.move(new_pos)
        elif self.resizing:
            # 리사이징 중이면 위젯 크기 조정
            self.resize_overlay(event.globalPosition().toPoint())
        else:
            # 마우스 커서 모양 변경
            edge = self.get_resize_edge(event.position().toPoint())
            if edge in ['top', 'bottom']:
                self.setCursor(Qt.SizeVerCursor)
            elif edge in ['left', 'right']:
                self.setCursor(Qt.SizeHorCursor)
            elif edge in ['top_left', 'bottom_right']:
                self.setCursor(Qt.SizeFDiagCursor)
            elif edge in ['top_right', 'bottom_left']:
                self.setCursor(Qt.SizeBDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # 마우스 버튼을 놓으면 드래그와 리사이징 종료
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_edge = None

    def get_resize_edge(self, pos):
        # 마우스 위치에 따라 리사이징 방향 결정
        x, y = pos.x(), pos.y()
        if x < self.border_thickness:
            if y < self.border_thickness:
                return 'top_left'
            elif y > self.height() - self.border_thickness:
                return 'bottom_left'
            return 'left'
        elif x > self.width() - self.border_thickness:
            if y < self.border_thickness:
                return 'top_right'
            elif y > self.height() - self.border_thickness:
                return 'bottom_right'
            return 'right'
        elif y < self.border_thickness:
            return 'top'
        elif y > self.height() - self.border_thickness:
            return 'bottom'
        return None

    def resize_overlay(self, pos):
        # 위젯 리사이징 수행
        new_geometry = self.geometry()
        global_pos = self.mapFromGlobal(pos)
        if self.resize_edge in ['left', 'top_left', 'bottom_left']:
            new_geometry.setLeft(self.mapToParent(global_pos).x())
        if self.resize_edge in ['right', 'top_right', 'bottom_right']:
            new_geometry.setRight(self.mapToParent(global_pos).x())
        if self.resize_edge in ['top', 'top_left', 'top_right']:
            new_geometry.setTop(self.mapToParent(global_pos).y())
        if self.resize_edge in ['bottom', 'bottom_left', 'bottom_right']:
            new_geometry.setBottom(self.mapToParent(global_pos).y())
        
        # 최소 크기 제한
        if new_geometry.width() < 50:
            if 'right' in self.resize_edge:
                new_geometry.setRight(new_geometry.left() + 50)
            else:
                new_geometry.setLeft(new_geometry.right() - 50)
        if new_geometry.height() < 50:
            if 'bottom' in self.resize_edge:
                new_geometry.setBottom(new_geometry.top() + 50)
            else:
                new_geometry.setTop(new_geometry.bottom() - 50)
        
        self.setGeometry(new_geometry)

class OCRMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        # 투명 오버레이 위젯 생성 및 표시
        self.overlay = TransparentOverlay()
        self.overlay.setGeometry(100, 100, 300, 300)
        self.overlay.show()
        self.client = None

    def initUI(self):
        self.setWindowTitle("OCR 캡쳐")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # JSON 키 파일 경로 입력 필드
        self.json_path_input = QLineEdit(self)
        self.json_path_input.setPlaceholderText("JSON 키 파일 경로를 입력하세요 => ex) C:/Users/dhk93/OneDrive/Desktop/key/rpaacr-424a14-e50490e653c4.json")
        layout.addWidget(self.json_path_input)

        # JSON 경로 업데이트 버튼
        self.update_json_button = QPushButton("JSON 경로 업데이트", self)
        self.update_json_button.clicked.connect(self.update_json_path)
        layout.addWidget(self.update_json_button)

        # JSON 키 발급 방법 토글 버튼
        self.show_instruction_button = QPushButton("JSON 키 발급 방법 보기", self)
        self.show_instruction_button.clicked.connect(self.toggle_instruction)
        layout.addWidget(self.show_instruction_button)

        # JSON 키 발급 방법 설명 라벨 (처음에는 숨김)
        self.instruction_label = QLabel()
        self.instruction_label.setWordWrap(True)
        self.instruction_label.hide()
        layout.addWidget(self.instruction_label)

        # 스크롤 가능한 영역 생성
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # OCR 결과 이미지 표시 라벨
        self.ocr_label = QLabel()
        self.ocr_label.setFixedSize(400, 400)
        scroll_layout.addWidget(self.ocr_label)

        # OCR 결과 텍스트 표시 영역
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        scroll_layout.addWidget(self.text_edit)

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        # 캡처 버튼
        self.capture_button = QPushButton("캡쳐하기")
        self.capture_button.clicked.connect(self.captureAndOCR)
        layout.addWidget(self.capture_button)

    def closeEvent(self, event):
        # 메인 윈도우가 닫힐 때 오버레이도 함께 닫기
        self.overlay.close()
        super().closeEvent(event)

    def update_json_path(self):
        # JSON 키 파일 경로 업데이트 및 클라이언트 초기화
        json_path = self.json_path_input.text()
        try:
            self.client = vision.ImageAnnotatorClient.from_service_account_json(json_path)
            self.text_edit.setText("JSON 경로가 성공적으로 업데이트되었습니다.")
        except Exception as e:
            self.text_edit.setText(f"JSON 경로 업데이트 오류: {str(e)}")

    def toggle_instruction(self):
        # JSON 키 발급 방법 설명 토글
        if self.instruction_label.isHidden():
            instruction_text = """
            JSON 키 발급 방법:
            1. Google API Developer Console에 접속 (구글에서 검색)
            2. 새 프로젝트 만들기
            3. 검색창에 Cloud Vision API 검색하고 사용 클릭
            4. 사용자 인증 정보 탭 클릭
            5. 사용자 인증 정보 만들기
            6. 서비스 계정 => 이메일 클릭
            7. 키 탭으로 이동
            8. 키 추가 => 새 키 만들기
            9. JSON으로 발급
            10. 발급받은 JSON 키 경로를 위 입력란에 입력하세요
            """
            self.instruction_label.setText(instruction_text)
            self.instruction_label.show()
            self.show_instruction_button.setText("JSON 키 발급 방법 숨기기")
        else:
            self.instruction_label.hide()
            self.show_instruction_button.setText("JSON 키 발급 방법 보기")

    def captureAndOCR(self):
        # Google Cloud Vision 클라이언트가 초기화되지 않았다면 에러 메시지 표시
        if self.client is None:
            self.text_edit.setText("먼저 JSON 키 파일 경로를 설정해 주세요.")
            return

        # 화면 캡처
        screen = QApplication.primaryScreen()
        screenshot = screen.grabWindow(0, self.overlay.x(), self.overlay.y(), 
                                       self.overlay.width(), self.overlay.height())
        
        # 캡처한 이미지 표시
        self.ocr_label.setPixmap(screenshot.scaled(400, 400, Qt.KeepAspectRatio))

        # 캡처한 이미지를 numpy 배열로 변환
        qimage = screenshot.toImage()
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.constBits()
        arr = np.array(ptr).reshape(height, width, 4)
        img = arr[:, :, :3]

        # 이미지 색상 변환 및 인코딩
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        _, encoded_img = cv2.imencode('.png', img)
        content = encoded_img.tobytes()

        # Google Cloud Vision API를 사용하여 OCR 수행
        image = vision.Image(content=content)
        response = self.client.text_detection(image=image)
        texts = response.text_annotations

        # OCR 결과 표시
        if texts:
            self.text_edit.setText(texts[0].description)
        else:
            self.text_edit.setText("텍스트가 감지되지 않았습니다.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OCRMainWindow()
    window.show()
    sys.exit(app.exec())