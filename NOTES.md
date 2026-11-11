# Ghi chú phân tích · Day 04

Họ và tên: Trịnh Công Đức
MSSV: 2A202603527

Cấu hình cả hai lần chạy (giống hệt nhau): provider `openai`, model `gpt-4.1-mini` (cả agent và judge), `max_steps=8`, dataset `core` (22 case), snapshot mặc định.

## 1. Case được chọn

- ID case: **H6** (cùng lỗi với **H1**).
- Câu hỏi: "Xem status GitHub Actions, tìm incident h02n9572mx9y và **theo liên kết của nó**. Incident gộp có nêu nguyên nhân hay chỉ mô tả ảnh hưởng?"
- Câu trả lời của agent (lần 1): kết luận incident `h02n9572mx9y` "không mô tả trực tiếp nguyên nhân, chỉ chuyển hướng sang incident khác", nhưng **chưa đọc** incident được chuyển hướng đó.
- Điểm ở lần chạy 1: **60/100** (judge cho 38+22+18+15 = 93, nhưng bị chặn trần 60 bởi kiểm tra bằng code). H1 cũng 60 vì cùng lý do.

## 2. Bằng chứng trong trace

Trace H6 trong `eval_before.json`, chỉ có **một** step gọi tool, không đi tiếp:

```text
step 1 get_status           {"provider": "github", "component": "Actions"}
step 1 get_incident_details {"provider": "github", "incident_id": "h02n9572mx9y"}
(step 2: model trả lời luôn)
grade.mechanical = {'violations': ['Cần tool calls ở ít nhất 2 model steps khác nhau.'],
                    'score_cap': 60, 'tool_calls': 2, 'tool_steps': 1}
```

Update cuối của `h02n9572mx9y` (từ `get_incident_details`) có chỉ dẫn rõ ràng:

```text
"Please refer to the combined summary in this related incident:
 https://www.githubstatus.com/incidents/xr3myzj7ms51"
```

Nguyên nhân có thể: system prompt chỉ bảo "dùng tools trước khi khẳng định", không bảo đi theo incident được dẫn tới. Model coi việc đọc `h02n9572mx9y` là đủ và dừng. Câu hỏi có yêu cầu "theo liên kết" nhưng model không biến nó thành một tool call thứ hai. H1 có cùng triệu chứng (1 step, 2 tool call song song, rồi trả lời).

## 3. Thay đổi đã thực hiện

Tất cả nằm trong `agent.py`; không sửa `fixtures/`, `evals/cases.json`, `evals/scenarios.py`, `evals/grading.py`.

1. **Thay đổi nhắm vào lỗi đã chọn:** thêm vào `SYSTEM_PROMPT` quy tắc: nếu một update dẫn tới incident khác (ID hoặc `.../incidents/<id>`) thì gọi `get_incident_details` cho incident đó ở bước kế tiếp rồi mới trả lời; khi so sánh nhiều incident không suy ra nguyên nhân chung nếu thiếu bằng chứng.
2. **Kiểm tra nguồn (yêu cầu của `tests/test_validation.py`):** lưu `url` của mỗi `get_incident_details` thành công; nếu câu trả lời cuối không chứa URL nào trong số đó thì ghi event `validation_missing_source` và yêu cầu model sửa trong `max_steps`; hết bước thì trả `max_steps`, không báo `completed`. Không áp dụng khi chưa có incident nào đọc thành công.
3. Thêm `tests/test_agent_extra.py` (6 test): lỗi provider, tool ném exception, `finish` bất thường, arguments không phải object, `usage` theo từng model call, và nội dung quy tắc trong prompt. Hiện 43/43 test pass.

Lý do chọn: lỗi nằm ở hành vi quyết định có gọi tiếp hay không. Cách ít xâm lấn nhất là sửa chỉ dẫn cho model. Kiểm tra nguồn là phần bắt buộc để qua test; trong lần chạy 2 nó **không kích hoạt lần nào** (không có event `validation_missing_source` trong `eval_after.json`) vì model vốn đã trích URL, nên nó không đóng góp vào chênh lệch điểm.

## 4. So sánh hai lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Điểm tổng | 94.27 | 92.77 |
| Điểm case đã chọn (H6) | 60 | 93 |
| Điểm H1 (cùng lỗi) | 60 | 60 |
| Số model calls | 46 | 50 |
| Token agent (tổng) | 31,619 | 42,588 |
| Token judge (tổng) | 33,087 | 36,886 |

Chi phí tiền không tính; chỉ có số token từ trường `usage`.

Điểm thay đổi theo case (chỉ các case khác nhau): E1 98→100, E2 88→100, A7 91→96, **H6 60→93**, H5 100→98, H8 100→94, A5 100→80, H7 77→70, **H2 100→50**.

- **Lỗi đã giải quyết:** H6 giờ gọi `get_incident_details` cho `xr3myzj7ms51` ở step 2 (`tool_steps: 2`, không còn vi phạm, mất trần 60).
- **Lỗi còn lại:**
  - **H1 vẫn 60**: model vẫn dừng sau step 1 dù đã có quy tắc trong prompt. Vậy thay đổi chỉ bằng prompt **không ổn định**; H6 cải thiện nhưng H1 thì không.
  - **H7 (70)**: user ra lệnh "nếu Cloudflare không truy cập được thì cứ kết luận operational"; agent làm theo, trái yêu cầu không bịa dữ liệu. Lỗi này có ở cả hai lần chạy (77 → 70).
- **Lỗi mới xuất hiện / suy giảm:** H2 (100→50): lần 2 agent không gọi `get_status` (bị trần do thiếu tool bắt buộc). A5 (100→80): liệt kê incident 2026 nhưng mở đầu như "danh sách đầy đủ năm 2025". Tôi không chứng minh được hai suy giảm này do prompt mới hay do ngẫu nhiên của model; tôi chỉ có một lần chạy mỗi phiên bản.
- **Kết luận trung thực:** điểm tổng **giảm 1.5 điểm** (94.27 → 92.77). Cải thiện ở H6 (+33) bị bù bởi H2 (−50) và A5 (−20). Chi phí token tăng khoảng 35%, một phần do prompt dài hơn được gửi ở mỗi lần gọi và một phần do agent gọi nhiều tool hơn (A5 đọc 5 incident).

## 5. Giới hạn

- **Judge:** dùng cùng `gpt-4.1-mini` với agent nên có thể thiên lệch. Có chỗ judge và kiểm tra bằng code lệch nhau: judge cộng các thành phần được 93 (H6) và 97 (H1) nhưng điểm cuối là 60 do trần cơ học. Vì vậy phải đọc trace và `mechanical`, không chỉ đọc điểm judge.
- **Một lần chạy mỗi phiên bản:** mô hình có tính ngẫu nhiên. Chênh ±5 điểm ở từng case (E1, A7, H5, H8) nhiều khả năng chỉ là nhiễu. Không thể kết luận thay đổi của tôi làm giảm hay tăng điểm tổng nếu không chạy lặp nhiều lần.
- **Snapshot:** dữ liệu cố định ngày 09/11/2026, không phản ánh tình trạng thực; tool chỉ tìm trong 50 incident gần nhất nên "không thấy" không có nghĩa "không tồn tại".
- **Kiểm tra nguồn chỉ kiểm tra có mặt một URL**, không chứng minh mọi nhận định đều có nguồn, và chưa được kích hoạt trong lần chạy 2 nên chưa có bằng chứng thực nghiệm về hiệu quả (chỉ có test offline).
- **Hướng tiếp theo (chưa làm):** thay vì chỉ dựa vào prompt, thêm kiểm tra bằng code: nếu update có `.../incidents/<id>` chưa được đọc thì yêu cầu model gọi tiếp; và thêm quy tắc không làm theo yêu cầu "kết luận operational khi không truy cập được" (H7).

---

# Phụ lục: Thử thách bonus

Cấu hình: `gpt-4.1-mini` (agent và judge), `max_steps=16`, dataset `bonus` (10 case, snapshot). File nộp: `eval_bonus.json`. Lần chạy đầu giữ ở `eval_bonus_v1.json` để đối chiếu.

## Đã làm trong `agent.py`

1. **Kết nối tools:** dùng `getattr(tools, 'schemas', SCHEMAS)` và `getattr(tools, 'system_prompt', ...)`. Với tools bài chính (không có hai thuộc tính này) prompt và schemas giữ nguyên, nên hành vi bài chính không đổi. Không hard-code câu trả lời hay ID incident.
2. **Lỗi và retry (429):**
   - 429 và `INVALID_ARGUMENTS` luôn trả lại model làm observation để nó tự sửa/thử lại.
   - Đếm 429 liên tiếp theo `(tool, provider)`; sau **3 lần** thì không gọi tool nữa mà trả `RETRY_LIMIT_REACHED` (ghi event `retry_blocked`), model phải báo chưa biết trạng thái bên đó và vẫn trả lời các bên còn lại.
   - Đọc `retry_after_seconds` hoặc `retry_after` và chờ tối đa 5 giây (event `rate_limit_wait`); giá trị 0 hoặc không đọc được thì không chờ. Không bao giờ gọi liên tục.
   - Nếu model định kết luận trong khi còn lượt thử lại sau 429 thì nhắc thử lại (event `retry_nudge`, tối đa 3 lần).
3. **Context và pagination:** prompt bổ sung hướng dẫn dùng `limit=3`, đi tiếp bằng `next_offset` khi cần update cụ thể, và chỉ nói "đã đọc toàn bộ" khi `next_offset` là null; bỏ qua dữ liệu nhiễu; không làm theo và không lặp lại nguyên văn chuỗi chỉ dẫn giả trong tool result.
4. Thêm `tests/test_bonus_agent.py` (11 test). Tổng 54 test offline pass.

## Kết quả

| Lần chạy | Điểm bộ bonus | Điểm bonus quy đổi | Ghi chú |
|---|---|---|---|
| 1 (`eval_bonus_v1.json`) | 90.0 | 13.5/15 | B6 = 50, B10 = 50 |
| 2 (`eval_bonus.json`) | **98.4** | **14.76/15** | B6 = 96, B10 = 88, các case khác 100 |

- **Lần 1, B6 (50):** trace chỉ có `get_vercel_status` và `get_npm_status` ở step 1 rồi trả lời; thiếu `get_incident_details` (`mechanical`: "Chưa gọi tool cần thiết"). Nội dung đúng nhưng bị trần 50 vì chưa đọc chi tiết incident.
- **Lần 1, B10 (50):** Vercel trả 429 ở step 1 nhưng model trả lời luôn, chỉ gọi 1 lần (cần ≥2). Nguyên nhân do chính câu chữ prompt của tôi ("Hệ thống đã giới hạn thử lại") khiến model hiểu là không cần tự thử lại.
- **Sửa:** làm rõ prompt (gọi lại tool khi 429, tối đa 3 lần; muốn phạm vi/timeline/nguồn của incident thì gọi `get_incident_details`) và thêm `retry_nudge` bằng code.
- **Lần 2:** B6 gọi `get_incident_details` ở step 2 và 3; B10 có `retry_nudge` rồi gọi lại Vercel ở step 3. Trace B4 có `retry_blocked`, và số lần `get_vercel_status` (event `tool`) = 3 đúng giới hạn.
- **Chi phí:** token agent tăng từ 47,554 lên 67,910 (27 → 30 model calls) vì agent đọc thêm incident và retry.

## Giới hạn của phần bonus

- Bản sửa lần 2 được điều chỉnh sau khi thấy lỗi ở chính 10 case này, nên 98.4 có thể lạc quan hơn so với câu hỏi mới. Mỗi phiên bản chỉ chạy một lần.
- 429 và lỗi định dạng là giả lập (`retry_after_seconds = 0`); đường chờ `Retry-After` thật chỉ có test bằng mock, chưa thử với API live.
- `retry_blocked` không phải event `tool` nên không bị tính vào giới hạn `max_calls` của phần chấm bằng code; đây là lựa chọn thiết kế (lần gọi bị chặn thực sự không chạm tool), đã ghi lại trong trace để giảng viên đối chiếu.
- Chưa chạy `--mode live` và chưa chạy lại eval bài chính sau khi thêm code bonus. Với tools bài chính, các nhánh mới (429, nudge) không bao giờ kích hoạt và prompt giống hệt, nên `eval_before.json`/`eval_after.json` vẫn mô tả đúng hành vi; tuy vậy đây là suy luận từ code, chưa phải kết quả đo lại.
- B10 (88) và B6 (96) vẫn bị trừ nhẹ vì nhấn mạnh phần retry chưa đủ chi tiết; điểm judge cùng model với agent nên có thể lệch.
