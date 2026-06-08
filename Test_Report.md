# BÁO CÁO KIỂM THỬ VÀ ĐÁNH GIÁ (TEST REPORT)

Dự án: **Hệ thống cốt truyện nhập vai tương tác sử dụng trí tuệ nhân tạo (AI Story Adventure)**  
Thời gian báo cáo: 08/06/2026  

---

## 1. CHIẾN LƯỢC KIỂM THỬ (TEST STRATEGY)

Để đảm bảo chất lượng, tính ổn định và khả năng phản hồi của hệ thống cốt truyện tương tác tự sinh, dự án áp dụng chiến lược kiểm thử phân tầng kết hợp giữa thử nghiệm ngoại tuyến cô lập (sử dụng dữ liệu giả lập) và kiểm thử trực tuyến (giao tiếp trực tiếp với các mô hình ngôn ngữ lớn).

Chiến lược được chia làm hai cấp độ chính:

### a. Kiểm thử đơn vị (Unit Testing)
Kiểm thử đơn vị tập trung vào việc xác thực độc lập tính đúng đắn của các cấu trúc dữ liệu, các công thức toán học, các thuật toán cốt lõi và cơ chế **chỉ số chiến đấu (Combat Stat)** mới được bổ sung mà không cần kết nối với hệ quản trị cơ sở dữ liệu vật lý hoặc các dịch vụ mạng.
* **Đối tượng kiểm thử:**
  * **Các thực thể trong trò chơi:** Xác thực các thuộc tính, thông số khởi tạo và ràng buộc dữ liệu của nhân vật, địa điểm, nhiệm vụ, ký ức và các loại vật phẩm (như bình thuốc phục hồi, vũ khí, vật phẩm nhiệm vụ và vật phẩm thường).
  * **Quản lý trạng thái người chơi:** Kiểm tra công thức tính toán lượng máu và trừ sát thương thực tế dựa theo phòng thủ của nhân vật, cơ chế đeo và tháo vũ khí để cập nhật sức mạnh, sử dụng vật phẩm tiêu hao để hồi phục, theo dõi tiến độ nhiệm vụ và chuyển đổi toàn bộ trạng thái chơi sang dạng văn bản mã hóa để chuẩn bị lưu trữ.
  * **Thuật toán sắp xếp thứ tự ký ức:** Kiểm tra tính chính xác của thuật toán chấm điểm và sắp xếp lại độ ưu tiên ký ức dựa trên hệ số suy giảm theo thời gian, điểm thưởng địa điểm tương thích và điểm thưởng từ khóa tìm kiếm.
  * **Bộ xử lý và tách định dạng văn bản:** Đảm bảo bóc tách chính xác các đoạn hội thoại có thẻ tên nhân vật hoặc tự động nhận diện lời thoại của nhân vật phụ thông qua các quy tắc dấu ngoặc kép dự phòng.
  * **Cơ chế chỉ số chiến đấu:** Đảm bảo tính nhất quán số liệu đầu ra của người chơi (vũ khí, sát thương cơ bản, trạng thái máu HP, độ nhanh nhẹn) khi tạo các chỉ thị để tác nhân cốt truyện (StoryAgent) làm căn cứ kể chuyện.

### b. Kiểm thử kết hợp (Integration Testing)
Kiểm thử kết hợp tập trung xác thực luồng truyền nhận thông tin giữa các thành phần liên kết, sự đồng bộ dữ liệu vào cơ sở dữ liệu, sự tích hợp sát thương chiến đấu từ tác nhân AI và khả năng kết nối mạng từ máy chủ web điều phối backend đến các tác nhân trí tuệ nhân tạo trực tuyến.
* **Đối tượng kiểm thử:**
  * **Vòng đời cơ sở dữ liệu:** Thử nghiệm quy trình khởi tạo cơ sở dữ liệu, tạo bảng thông tin bối cảnh, lưu trữ thông tin nhân vật và địa điểm có liên kết ràng buộc khóa ngoại, ghi nhận ký ức liên quan đến nhân vật, tìm kiếm thực thể bằng từ khóa và dọn sạch dữ liệu bối cảnh sau khi kết thúc trò chơi.
  * **Cổng kết nối ứng dụng (API Endpoints):** Xác thực khả năng phản hồi của các cổng giao tiếp, kiểm tra trạng thái sẵn sàng của hệ thống, kiểm tra tính hợp lệ của khóa kết nối tác nhân, truy vấn trạng thái nhân vật chơi và xuất nhật ký lịch sử hành trình.
  * **Tác nhân trí tuệ nhân tạo trực tuyến:** Kích hoạt chế độ kiểm thử kết nối mạng trực tiếp để gửi yêu cầu thật và xác thực định dạng phản hồi từ các mô hình ngôn ngữ lớn trên đám mây:
    * **Tác nhân định tuyến ý định hành động** (kết nối trực tiếp với dịch vụ của Google).
    * **Tác nhân quản lý nhạc nền bối cảnh** (kết nối trực tiếp với dịch vụ của Google).
    * **Tác nhân sinh menu lựa chọn nhập vai** (kết nối trực tiếp với dịch vụ đám mây của Groq).
    * **Tác nhân tối ưu câu truy vấn bộ nhớ ký ức** (kết nối trực tiếp với dịch vụ đám mây của Groq).
  * **Tích hợp tính toán sát thương chiến đấu:** Kiểm thử tích hợp xử lý trừ máu của trạng thái người chơi dựa trên lượng sát thương được trích xuất tự động bởi tác nhân chiến đấu từ văn bản cốt truyện (story response).

---

## 2. DANH SÁCH CÁC CA KIỂM THỬ (TEST CASES)

Hệ thống sở hữu tổng cộng **38 ca kiểm thử** tự động được thiết lập thông qua tệp cấu hình thử nghiệm chung. Toàn bộ các ca kiểm thử đều vượt qua thành công (**Passed 100%**). Dưới đây là mô tả chi tiết bằng ngôn ngữ tự nhiên:

### A. Kiểm thử Đơn vị (Unit Tests - 26 Ca)

| STT | Thành phần kiểm thử | Kịch bản / Dữ liệu đầu vào (Input Scenario) | Kết quả trả về mong muốn (Expected Outcome) | Kết quả |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Khởi tạo thực thể | Tạo thực thể vật lý cơ bản mang tên `"Cổng cổ xưa"`, mô tả `"Một chiếc cổng làm từ đá cổ xưa"`, kiểu thực thể `"object"`. | Thực thể được tạo thành công, giữ đúng tên, mô tả và kiểu dữ liệu như thiết kế. | Passed |
| 2 | Khởi tạo vật phẩm tiêu hao | Tạo vật phẩm `"Bình máu lớn"`, hiệu ứng hồi phục: HP +50, Sức mạnh +5. | Khởi tạo thành công vật phẩm tiêu dùng mang đúng chỉ số cộng thêm; các chỉ số phòng thủ và nhanh nhẹn mặc định bằng 0. | Passed |
| 3 | Khởi tạo vũ khí | Tạo vũ khí `"Thánh kiếm Eldoria"`, sát thương cơ bản: 100, bổ trợ: Sức mạnh +15, hiệu ứng: "Burn", tỉ lệ kích hoạt: 25%. | Khởi tạo thành công vũ khí mang đúng các thuộc tính, bộ sửa đổi chỉ số và hiệu ứng đặc biệt. | Passed |
| 4 | Khởi tạo vật phẩm nhiệm vụ | Tạo vật phẩm `"Chìa khóa ngục tối"`, được gắn nhãn liên kết với nhiệm vụ `"Quest_Mở_Cửa"`. | Khởi tạo thành công vật phẩm có kiểu dữ liệu là vật phẩm nhiệm vụ và lưu đúng tên nhiệm vụ liên kết. | Passed |
| 5 | Khởi tạo vật phẩm phụ | Tạo vật phẩm `"Đá vụn"` không có hiệu ứng đặc biệt. | Khởi tạo thành công vật phẩm thuộc kiểu vật phẩm linh tinh. | Passed |
| 6 | Khởi tạo nhiệm vụ | Tạo nhiệm vụ `"Giải cứu vương quốc"`, mô tả chi tiết, gồm 3 mục tiêu, người giao là `"Nhà vua"`. | Khởi tạo nhiệm vụ thành công với trạng thái ban đầu là mảng bit `[0, 0, 0]` (biểu thị cả 3 mục tiêu đều chưa hoàn thành). | Passed |
| 7 | Khởi tạo địa điểm | Tạo địa điểm `"Rừng thiêng"`, bầu không khí `"Huyền bí"`, đường dẫn ảnh `"images/forest.png"`. | Khởi tạo địa điểm thành công, lưu giữ chính xác tên, mô tả và tài nguyên hình ảnh đi kèm. | Passed |
| 8 | Khởi tạo nhân vật (NPC) | Tạo nhân vật `"Elara"`, tính cách `"Thân thiện"`, thiện cảm ban đầu: 50, vị trí: `"Thành phố Eldoria"`. | Khởi tạo nhân vật thành công với trạng thái bình thường và các thuộc tính tương tác chính xác. | Passed |
| 9 | Lớp lưu trữ ký ức | Khởi tạo đối tượng ký ức tại `"Thị trấn khởi đầu"`, nội dung: `"Nói chuyện với Elara"`, tại lượt chơi thứ 1. | Lưu trữ chính xác dữ liệu bối cảnh không gian, nội dung cuộc hội thoại và lượt chơi tương ứng. | Passed |
| 10 | Cơ chế suy giảm ký ức | Có 3 ký ức ở các lượt 1, 2, 3. Thực hiện sắp xếp ở lượt 4 với hệ số suy giảm thời gian là $0.05$. | Ký ức ở lượt 3 (mới nhất) được ưu tiên xếp đầu tiên, ký ức lượt 1 (cũ nhất) xếp cuối cùng. | Passed |
| 11 | Điểm thưởng địa điểm | Sắp xếp các ký ức khi người chơi đang đứng ở `"Eldoria Great Hall"`. Có 2 ký ức ở `"Eldoria Great Hall"`, 1 ký ức ở `"Foggy Forest"`. | Các ký ức tại địa điểm trùng khớp nhận điểm thưởng +20% (hệ số x1.2) và vọt lên xếp trên ký ức không trùng. | Passed |
| 12 | Điểm thưởng từ khóa | Tìm kiếm ký ức với từ khóa tìm kiếm: `["sói", "xám"]`. Có 1 ký ức chứa cụm từ này trong văn bản. | Ký ức chứa từ khóa nhận điểm thưởng +15% mỗi từ khớp (tổng +30%), vọt lên vị trí ưu tiên số 1 bất chấp độ cũ/mới. | Passed |
| 13 | Tính toán sát thương | Nhân vật có phòng thủ 5, nhận sát thương thô lần lượt là 50 và 60. | Tính đúng sát thương thực tế theo công thức $\text{Damage} - 0.5 \times \text{Defense}$. HP giảm từ 100 xuống 52, rồi xuống 0 (nhân vật chuyển sang trạng thái tử vong). | Passed |
| 14 | Trang bị vũ khí | Nhân vật có sức mạnh gốc 10, trang bị `"Kiếm sắt"` (+5 sức mạnh), sau đó đổi sang `"Kiếm vàng"` (+15 sức mạnh), sau đó tháo vũ khí. | Sức mạnh tăng lên 15 khi cầm kiếm sắt; đổi sang kiếm vàng sức mạnh tăng lên 25 (hệ số cũ bị xóa); khi tháo ra sức mạnh trả về 10. | Passed |
| 15 | Sử dụng vật phẩm tiêu hao | Nhân vật bị mất máu còn 72 HP, sử dụng `"Bình máu nhỏ"` (hồi 20 HP) từ trong balo. | HP tăng lên đúng 92, đồng thời `"Bình máu nhỏ"` bị xóa bỏ hoàn toàn khỏi danh sách vật phẩm trong balo. | Passed |
| 16 | Quản lý nhiệm vụ | Nhân vật được giao nhiệm vụ chính và nhiệm vụ phụ. | Hệ thống theo dõi chính xác danh sách nhiệm vụ đang thực hiện và hiển thị đúng nhiệm vụ chính hiện tại. | Passed |
| 17 | Tuần tự hóa thông tin | Nhân vật Arthur đang đứng ở `"Làng"`, sở hữu các vật phẩm và chỉ số máu tương ứng. | Xuất ra cấu trúc văn bản chứa đầy đủ dữ liệu, hòm đồ, nhiệm vụ và các chỉ số sức mạnh của nhân vật. | Passed |
| 18 | Tải lại trạng thái game | Đọc cấu trúc văn bản lưu trữ: Arthur ở `"Thành cổ"`, máu 85, đang làm nhiệm vụ `"Tìm chìa khóa"`. | Khôi phục chính xác trạng thái nhân vật chơi, tự động phân giải các liên kết dạng chuỗi thành đối tượng nhân vật và địa điểm thực tế trong cơ sở dữ liệu. | Passed |
| 19 | Bộ tách chữ (Thẻ đối thoại) | Gửi chuỗi: `"Bóng đêm... [NPC_TALK: Elara]Hãy đi lối này![/NPC_TALK] [PLAYER_TALK]Tôi hiểu rồi.[/PLAYER_TALK]"` | Tách chính xác thành 3 phân đoạn: Master dẫn chuyện, Elara nói chuyện (`"Hãy đi lối này!"`) và người chơi nói chuyện (`"Tôi hiểu rồi."`). | Passed |
| 20 | Bộ tách chữ (Thẻ ẩn danh) | Gửi chuỗi hội thoại chứa thẻ nhân vật ẩn danh: `"[NPC_TALK]Chào người lạ mặt.[/NPC_TALK]"` | Tách đúng phân đoạn hội thoại và gán người nói mặc định là `"NPC"`. | Passed |
| 21 | Bộ tách chữ (Ngoặc kép) | Gửi chuỗi tự sự xen hội thoại: `"Elara nhìn tôi. "Hãy cẩn thận trên đường đi!" Cô ấy đưa thuốc."` | Tách thành công phần trong ngoặc kép thành lời thoại của nhân vật phụ, các phần ngoài ngoặc kép là lời dẫn truyện của Master. | Passed |
| 22 | Bộ tách chữ (Tự sự thuần) | Gửi chuỗi văn bản không chứa thẻ hay ngoặc kép: `"Vương quốc sụp đổ. Chỉ còn đống đổ nát."` | Hệ thống bóc tách tất cả các câu thành phân đoạn tự sự được kể bởi `"Master"`. | Passed |
| 23 | Bộ tách chữ (Chuỗi rỗng) | Gửi chuỗi văn bản rỗng. | Trả về một mảng rỗng an toàn mà không xảy ra bất kỳ lỗi hệ thống nào. | Passed |
| 24 | Chỉ thị chiến đấu (Thành công) | Khởi tạo người chơi `"TestHero"` có chỉ số Sức mạnh 15, Nhanh nhẹn 12, Phòng thủ 5, máu HP 100/100 và đánh tay không. Gọi sinh chỉ thị chiến đấu thành công. | Trả về chuỗi chỉ thị chiến đấu chứa thông tin: vũ khí đánh `"tay không"`, trạng thái `"còn khỏe mạnh (HP 100/100)"` và kết quả đánh trúng `"Outcome: Player's attack LANDS"`. | Passed |
| 25 | Chỉ thị chiến đấu (Thất bại) | Khởi tạo người chơi `"TestHero"` có HP 30/100, trang bị vũ khí `"Thánh kiếm"` (sát thương 25, hiệu ứng thiêu đốt `"burn"`, tỷ lệ kích hoạt 100%). Gọi sinh chỉ thị chiến đấu thất bại. | Trả về chuỗi chỉ thị chiến đấu chỉ ra hiệu ứng thiêu đốt được kích hoạt trên vũ khí `"Thánh kiếm"` và kết quả hành động thất bại `"Outcome: Player's attack MISSES or is COUNTERED"`. | Passed |
| 26 | Trích xuất sát thương AI | Gửi chuỗi văn bản: `"Con quái vật vung vuốt sắc bén cào trúng ngực bạn, gây 12 sát thương."` tới bộ trích xuất thông tin chiến đấu AI. | Trả về cấu trúc dữ liệu JSON chính xác chứa thông tin lượng sát thương gánh chịu: `{"taken_damage": 12}`. | Passed |

### B. Kiểm thử Tích hợp (Integration Tests - 12 Ca)

| STT | Thành phần kiểm thử | Kịch bản / Dữ liệu đầu vào (Input Scenario) | Kết quả trả về mong muốn (Expected Outcome) | Kết quả |
| :--- | :--- | :--- | :--- | :--- |
| 27 | Cơ sở dữ liệu | Khởi tạo cơ sở dữ liệu tạm thời, tạo bảng, thêm địa điểm `"Eldoria Great Hall"`, thêm nhân vật `"Priest Joseph"`, thêm ký ức, chạy tìm kiếm mờ `"Joseph"`. | Thực hiện lưu trữ thành công (ràng buộc khóa ngoại hoạt động tốt), tìm kiếm mờ trả về đúng nhân vật, và dọn sạch cơ sở dữ liệu thành công. | Passed |
| 28 | Cổng kiểm tra trạng thái | Gửi yêu cầu kiểm tra trạng thái hoạt động của máy chủ backend. | Trả về mã trạng thái thành công kèm nội dung xác nhận máy chủ đã sẵn sàng. | Passed |
| 29 | Cấu hình tác nhân (Thành công) | Gửi yêu cầu thiết lập cấu hình kèm các khóa kết nối tác nhân hợp lệ. | Trả về thông tin xác nhận kết nối thành công với các tác nhân trí tuệ nhân tạo. | Passed |
| 30 | Cấu hình tác nhân (Thất bại) | Gửi yêu cầu thiết lập cấu hình kèm các khóa kết nối tác nhân sai hoặc rỗng. | Trả về thông tin từ chối và báo lỗi khóa không hợp lệ. | Passed |
| 31 | Truy vấn bối cảnh người chơi | Gửi yêu cầu truy xuất trạng thái khi người chơi đang có máu 85, cầm `"Búa rèn"`, làm nhiệm vụ `"Rèn kiếm thần"`. | Phản hồi đúng dữ liệu chứa các thuộc tính thực tế của người chơi mà không bị lỗi cấu trúc. | Passed |
| 32 | Nhật ký hành trình | Gửi yêu cầu truy xuất nhật ký hành trình của người chơi. | Trả về đầy đủ danh sách tất cả các địa điểm đã đi qua, nhân vật đã gặp và nhiệm vụ đã nhận. | Passed |
| 33 | Lỗi trang bị vật phẩm | Gửi yêu cầu trang bị vật phẩm không có trong balo: `"Kiếm rỉ"`. | Trả về thông tin thất bại có kiểm soát và thông báo không thể trang bị. | Passed |
| 34 | Tích hợp tính sát thương combat | Khởi tạo người chơi `"Warrior"` có HP 100/100, Phòng thủ 10. Gửi chuỗi câu chuyện: `"Bạn bị tấn công bởi yêu tinh rừng."` và giả lập tác nhân chiến đấu trả về sát thương thô 20 đơn vị. | Sát thương thực tế được tính toán là $20 - 0.5 \times 10 = 15$ đơn vị. Cập nhật lượng máu HP của người chơi giảm xuống còn 85/100. | Passed |
| 35 | Định tuyến ý định AI (Trực tuyến) | Gửi câu lệnh hành động: `"Tôi muốn mở chiếc hòm gỗ cổ xưa kia"` qua cổng kết nối thực tế tới mô hình ngôn ngữ lớn của Google. | Phân tích chính xác ý định hành động tương tác vật lý với hòm gỗ dưới dạng cấu trúc dữ liệu chuẩn. | Passed |
| 36 | Lựa chọn nhập vai AI (Trực tuyến) | Gửi ngữ cảnh bối cảnh tại `"Lâu đài hoang"`, gặp nhân vật `"Elara"`, đang làm nhiệm vụ `"Tìm lối thoát"` tới mô hình ngôn ngữ lớn của Groq. | Sinh thành công danh sách các lựa chọn nhập vai chứa đủ các thuộc tính chỉ định, văn bản hành động và phong cách chơi. | Passed |
| 37 | Điều phối nhạc nền AI (Trực tuyến) | Gửi văn bản mô tả bối cảnh đáng sợ chứa tiếng bước chân và tiếng sói hú tới mô hình ngôn ngữ lớn của Google. | Trả về chính xác cảm xúc chủ đạo phân tích được là `"sợ hãi"` hoặc `"căng thẳng"` để điều phối nhạc nền phù hợp. | Passed |
| 38 | Tối ưu truy vấn ký ức AI (Trực tuyến) | Gửi địa điểm `"Rừng sâu"`, gặp nhân vật `"Elara"` và bối cảnh người chơi đi tìm thuốc tới mô hình ngôn ngữ lớn của Groq. | Sinh thành công một câu truy vấn từ khóa ngắn gọn tối ưu hóa cho bộ tìm kiếm nhúng ký ức. | Passed |

---

## 3. PHÂN TÍCH HIỆU NĂNG (PERFORMANCE ANALYSIS)

Kết quả đo lường hiệu năng thực thi của bộ kiểm thử được tách biệt rõ ràng giữa các môi trường để đảm bảo độ chính xác thực tế tuyệt đối:

### a. Hiệu năng Kiểm thử Ngoại tuyến (Offline Mode Performance)
* **Quy mô thực thi:** Chạy toàn bộ **34 ca kiểm thử** ngoại tuyến (từ ca 1 đến ca 34) trong môi trường giả lập hoàn toàn.
* **Tổng thời gian chạy:** **15.86 giây** (Bao gồm thời gian khởi động tiến trình kiểm thử, nạp các thư viện, nạp cơ sở dữ liệu tạm thời và kiểm tra các ca kiểm thử logic mới).
* **Thời gian xử lý logic cô lập:** Gần như tức thời (dưới **5 miligiây (ms)** cho mỗi ca kiểm thử) do toàn bộ kết nối cơ sở dữ liệu vật lý và các cổng dịch vụ ngoài đã được cô lập hoàn toàn trong bộ nhớ tạm thời.

### b. Hiệu năng Kiểm thử Trực tuyến (Online Mode Performance)
* **Quy mô thực thi:** Chạy toàn bộ **38 ca kiểm thử** (bao gồm 4 ca tích hợp trực tuyến gọi trực tiếp đến API thực tế của các nhà cung cấp tác nhân từ ca 35 đến ca 38).
* **Tổng thời gian chạy trực tuyến:** **22.74 giây** (Thời gian trung bình đo từ hệ thống kiểm thử tự động, bao gồm độ trễ mạng khi giao tiếp với API).
* **Chi tiết thời gian xử lý thực tế của từng ca kiểm thử trực tuyến (API Call Latency):**
  * **Tác nhân định tuyến ý định** (Ca 35 - Kết nối Google): **10.41 giây** (bao gồm thời gian thiết lập kết nối mã hóa bảo mật, gửi câu lệnh hành động và chờ phản hồi phân tích ý định).
  * **Tác nhân điều phối nhạc nền** (Ca 37 - Kết nối Google): **9.24 giây** (bao gồm thời gian phân tích ngữ nghĩa cảm xúc từ văn bản mô tả bối cảnh).
  * **Tác nhân sinh menu lựa chọn** (Ca 36 - Kết nối Groq sử dụng mô hình tối ưu): **0.83 giây** (bao gồm gửi bối cảnh game và sinh danh sách lựa chọn nhập vai).
  * **Tác nhân tối ưu câu truy vấn** (Ca 38 - Kết nối Groq sử dụng mô hình tối ưu): **0.80 giây** (bao gồm tổng hợp ngữ cảnh thành các từ khóa tìm kiếm bộ nhớ).
* **Nhận xét hiệu năng kết nối:** Tốc độ phản hồi của các tác nhân đám mây Groq cực kỳ nhanh (dưới 1 giây), chứng minh sự hiệu quả vượt trội trong việc sinh dữ liệu văn bản thời gian thực. Các tác nhân Google đòi hỏi thời gian xử lý dài hơn do khối lượng phân tích phức tạp hơn, tuy nhiên vẫn đảm bảo độ ổn định cấu trúc dữ liệu phản hồi đạt tuyệt đối 100%.

---

## 4. ĐÁNH GIÁ NGƯỜI DÙNG (USER EVALUATION)

*(Phần này đang được để trống và sẽ được cập nhật bổ sung sau khi người dùng trực tiếp trải nghiệm và đánh giá thực tế sản phẩm).*
