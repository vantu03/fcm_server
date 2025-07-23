import requests, pandas as pd, re, json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from io import BytesIO


class LichSinhVienICTU:
    def __init__(self, tk, mk):
        self.tk = tk
        self.mk = mk
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })

        self.today = datetime.today()
        self.result = {
            'status': 'success',
            'message': {
                'startDate': self.today.strftime("%d/%m/%Y"),
                'endDate': (self.today + timedelta(days=7)).strftime("%d/%m/%Y"),
                'schedule': []
            }
        }

    def extract_form_fields(self, form):
        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            if not name: continue
            input_type = input_tag.get('type', 'text')
            value = input_tag.get('value', '')
            if input_type in ['checkbox', 'radio']:
                if input_tag.has_attr('checked'):
                    form_data[name] = value
            else:
                form_data[name] = value
        for select in form.find_all('select'):
            name = select.get('name')
            if not name: continue
            selected_option = select.find('option', selected=True)
            form_data[name] = selected_option.get('value', '') if selected_option else \
                (select.find('option').get('value', '') if select.find('option') else '')
        for textarea in form.find_all('textarea'):
            name = textarea.get('name')
            if name:
                form_data[name] = textarea.text or ''
        return form_data

    def find_text_positions(self, df: pd.DataFrame, search_text: str, case_sensitive=False):
        matches = []
        for row_idx, row in df.iterrows():
            for col_idx, cell in enumerate(row):
                if pd.notna(cell):
                    cell_str = str(cell)
                    if (search_text in cell_str) if case_sensitive else (search_text.lower() in cell_str.lower()):
                        matches.append({"row": row_idx, "col": col_idx, "value": cell})
        return matches

    def get_study_time(self, tiet_start, tiet_end):
        tiet_map = {
            1: ("6:45", "7:35"), 2: ("7:40", "8:30"), 3: ("8:40", "9:30"),
            4: ("9:40", "10:30"), 5: ("10:35", "11:25"), 6: ("13:00", "13:50"),
            7: ("13:55", "14:45"), 8: ("14:55", "15:45"), 9: ("15:55", "16:45"),
            10: ("16:50", "17:40"), 11: ("18:15", "19:05"), 12: ("19:10", "20:00"),
            13: ("20:10", "21:00"), 14: ("21:10", "22:00"), 15: ("20:30", "21:30")
        }
        start = tiet_map.get(tiet_start, ("", ""))[0]
        end = tiet_map.get(tiet_end, ("", ""))[1]
        return f"{start} - {end}"

    def convert_time_to_minutes(self, time_range):
        if not time_range or not isinstance(time_range, str): return -1
        match = re.match(r'(\d{2}):(\d{2})', time_range)
        return int(match.group(1)) * 60 + int(match.group(2)) if match else -1

    def get_schedule(self):
        try:
            # Đăng nhập
            response = self.session.get('https://dangkytinchi.ictu.edu.vn/kcntt/login.aspx')
            soup = BeautifulSoup(response.text, 'html.parser')
            form_data = self.extract_form_fields(soup.find('form'))
            form_data['txtUserName'] = self.tk
            form_data['txtPassword'] = self.mk
            response = self.session.post(url=response.url, data=form_data)

            soup = BeautifulSoup(response.text, 'html.parser')
            lbl_error = soup.find(id="lblErrorInfo")
            if lbl_error and lbl_error.text.strip():
                self.result['status'] = 'error'
                self.result['message'] = lbl_error.text.strip()
                return self.result

            self.get_lich_hoc()
            self.get_lich_thi()

            self.result['message']['schedule'].sort(key=lambda x: (
                datetime.strptime(x['date'], '%d/%m/%Y') if x['date'] else datetime.max,
                self.convert_time_to_minutes(x.get('timeRange', ''))
            ))

            # Cập nhật startDate và endDate theo lịch thực tế
            dates = [x['date'] for x in self.result['message']['schedule'] if x.get('date')]
            if dates:
                self.result['message']['startDate'] = dates[0]
                self.result['message']['endDate'] = dates[-1]

        except requests.RequestException as e:
            self.result['status'] = 'error'
            self.result['message'] = f'Lỗi: {e}'
        return self.result

    def get_lich_hoc(self):
        response = self.session.get('https://dangkytinchi.ictu.edu.vn/kcntt/Reports/Form/StudentTimeTable.aspx')
        soup = BeautifulSoup(response.text, 'html.parser')
        form_data = self.extract_form_fields(soup.find('form'))
        # Lấy ngày hiện tại trừ đi 4 năm
        tu_ngay = datetime.today() - timedelta(days=365 * 1)
        form_data['txtTuNgay'] = tu_ngay.strftime('%d/%m/%Y')
        response = self.session.post(url=response.url, data=form_data)

        if not response.headers['Content-Type'].startswith('application/vnd.ms-excel') :
            return

        df = pd.read_excel(BytesIO(response.content), engine='xlrd')
        class_pos = self.find_text_positions(df, 'Lớp học phần')
        col_class = class_pos[0]['col']
        row_start = class_pos[0]['row'] + 1
        current_week_start = None
        session_counter = {}

        col_teacher = self.find_text_positions(df, 'Giảng viên/ link meet')[0]['col']
        col_day = self.find_text_positions(df, 'Thứ')[0]['col']
        col_period = self.find_text_positions(df, 'Tiết học')[0]['col']
        col_room = self.find_text_positions(df, 'Địa điểm')[0]['col']

        for i in range(row_start, len(df)):
            cell = df.iloc[i, col_class]

            if isinstance(cell, str) and cell.startswith("Tuần"):
                match = re.search(r"\((\d{2}/\d{2}/\d{4}) đến (\d{2}/\d{2}/\d{4})\)", cell)
                if match:
                    current_week_start = datetime.strptime(match.group(1), "%d/%m/%Y")
            elif pd.notna(cell) and current_week_start:
                try:
                    weekday = int(str(df.iloc[i, col_day]).strip())
                    date = current_week_start + timedelta(days=weekday - 2)
                except:
                    date = None

                session_counter.setdefault(cell, 0)
                session_counter[cell] += 1

                lichhoc = {
                    'date': date.strftime("%d/%m/%Y") if date else None,
                    'dayOfWeek': weekday,
                    'className': cell,
                    'scheduleType': 'Lịch học',
                    'timeRange': '00:00',
                    'detail': {
                        'Tiết': [],
                        'Địa điểm': str(df.iloc[i, col_room]).strip(),
                        'Buổi': session_counter[cell],
                    },
                    'hidden': {
                        'Giảng viên': str(df.iloc[i, col_teacher]).strip(),
                    },
                }

                self.result['message']['schedule'].append(lichhoc)

                period_raw = str(df.iloc[i, col_period]).strip()
                try:
                    parts = [int(p.strip()) for p in period_raw.split('-->')]
                    if len(parts) == 2:
                        tiet_start, tiet_end = parts
                        lichhoc['detail']['Tiết'] = list(range(tiet_start, tiet_end + 1))
                        lichhoc['timeRange'] = self.get_study_time(tiet_start, tiet_end)
                    elif len(parts) == 1:
                        tiet_start = tiet_end = parts[0]
                        lichhoc['detail']['Tiết'] = [tiet_start]
                        lichhoc['timeRange'] = self.get_study_time(tiet_start, tiet_end)
                except:
                    pass

    def get_lich_thi(self):
        response = self.session.get('https://dangkytinchi.ictu.edu.vn/kcntt/StudentViewExamList.aspx')
        soup = BeautifulSoup(response.text, 'html.parser')
        form_data = self.extract_form_fields(soup.find('form'))
        # Lấy ngày hiện tại trừ đi 4 năm
        tu_ngay = datetime.today() - timedelta(days=365 * 1)
        form_data['txtTuNgay'] = tu_ngay.strftime('%d/%m/%Y')
        response = self.session.post(url=response.url, data=form_data)

        if not response.headers['Content-Type'].startswith('application/vnd.ms-excel'):
            return

        df = pd.read_excel(BytesIO(response.content), engine='xlrd')
        class_pos = self.find_text_positions(df, 'Tên học phần')
        col_class = class_pos[0]['col']
        row_start = class_pos[0]['row'] + 1

        col_tc = self.find_text_positions(df, 'TC')[0]['col']
        col_day = self.find_text_positions(df, 'Ngày thi')[0]['col']
        col_period = self.find_text_positions(df, 'Thời gian thi')[0]['col']
        col_form = self.find_text_positions(df, 'Hình thức thi')[0]['col']
        col_sbd = self.find_text_positions(df, 'SBD')[0]['col']
        col_room = self.find_text_positions(df, 'Phòng thi')[0]['col']

        for i in range(row_start, len(df)):
            class_name = str(df.iloc[i, col_class]).strip()
            if not class_name or class_name.lower().startswith("nan"):
                continue

            try:
                date_obj = datetime.strptime(str(df.iloc[i, col_day]).strip(), "%d/%m/%Y")
                date = date_obj.strftime("%d/%m/%Y")
                day_of_week = date_obj.weekday() + 1
            except:
                date = None
                day_of_week = None

            time_range_match = re.search(r'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})', str(df.iloc[i, col_period]))
            time_range = f"{time_range_match.group(1)} - {time_range_match.group(2)}" if time_range_match else ""

            self.result['message']['schedule'].append({
                'date': date,
                'dayOfWeek': day_of_week,
                'className': class_name,
                'scheduleType': 'Lịch thi',
                'timeRange': time_range,
                'detail': {
                    'Ca thi': str(df.iloc[i, col_period]).strip(),
                    'Địa điểm': str(df.iloc[i, col_room]).strip()
                },
                'hidden': {
                    'Hình thức': str(df.iloc[i, col_form]).strip(),
                    'Số báo danh': str(df.iloc[i, col_sbd]).strip(),
                    'Số tín chỉ': str(df.iloc[i, col_tc]).strip()
                }
            })
