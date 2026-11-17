# BÁO CÁO BUILD HAI ADAPTER EXAMPLE — 2026-11-16

## TÓM TẮT NHANH CHO CHỦ TỊCH

- **Việc gì:** Đã biến example Codex CLI và Claude Code thành adapter chạy được, có broker admission, bằng chứng máy đọc và kiểm thử tích hợp.
- **An toàn hay nguy hiểm:** An toàn trong phạm vi build ngoại tuyến; không kết nối daemon thật, không dùng bí mật hoặc dữ liệu khách hàng, không triển khai live.
- **Rủi ro nếu duyệt:** Mock chỉ chứng minh hợp đồng ngoại tuyến; chưa chứng minh tương thích với broker daemon và upstream MCP thật.
- **Chủ tịch quyết gì:** Không cần quyết thêm để đóng build example; nghiệm thu live phải là gate riêng.
- **Khuyến nghị CEO:** Đóng build này; chỉ mở gate nghiệm thu live khi có broker daemon và upstream MCP fixture được kiểm soát.

## GATE_PROMPT — PHẠM VI ĐÃ ĐƯỢC GIAO

Build hai adapter example trong `examples/`: Codex CLI kết nối broker qua AF_UNIX, gửi tool name + argument hash, xử lý admit/block, sinh Evidence Manifest và có mock; Claude Code là MCP server dùng Python SDK `mcp`, admission trước khi forward, block khi bị từ chối, sinh evidence và có mock; mỗi adapter có ít nhất 5 test và README chạy thật/chạy test. Python 3.10+, không thêm dependency ngoài stdlib + `mcp`.

Ngoài phạm vi: broker daemon production, credential, dữ liệu khách hàng, deploy, go-live, sửa protocol/schema/validator, hoặc claim mock = live acceptance.

## KẾT QUẢ

- Codex CLI: client AF_UNIX một request/mỗi kết nối; request bind `tool` + SHA-256 canonical của arguments; kiểm kiểu và `call_id`; lỗi transport/timeout/response sai đều fail-closed; mọi lượt đều ghi manifest bằng create-new.
- Claude Code: MCP server thật; tool `governed_tool_call` gọi broker trước, chỉ mở upstream stdio MCP sau admission; block không forward; lỗi upstream được ghi `admitted: true` + `verdict: ERROR` để không trộn lỗi tool với từ chối governance.
- Mock broker: bật bằng `NODE1_MOCK_BROKER=1` hoặc `--mock`; commitment ghi rõ `mock-offline-not-live-authority`.
- MCP SDK: nhánh tương thích 1.x/2.x; môi trường kiểm thử thực tế dùng `mcp 2.2.0`.

## KIỂM THỬ

- Windows/Python 3.12: 16 ca, 15 đạt; 1 ca AF_UNIX được bỏ qua vì Windows không có `socket.AF_UNIX` trong runtime này.
- WSL/Linux: Codex 7/7 đạt, gồm ca AF_UNIX thật với mock broker socket.
- MCP integration: gọi tool qua `MCPServer.call_tool` của SDK, đi xuyên adapter → mock admission → mock forwarder → evidence.
- Standalone: `codex_adapter.py --mock` chạy thành công.
- JSON Schema: manifest sinh từ standalone đạt `evidence_manifest.schema.json`.
- `git diff --check`: không có lỗi whitespace; cảnh báo LF→CRLF là cấu hình working tree Windows, không phải lỗi nội dung.

## LESSON_RECALL_APPLIED

- **query:** lane CORE; domain governance, security, IPC, adapters, testing; risk ORANGE; build hai adapter admission/evidence/mock/integration.
- **retrieved:** L-163, L-165, L-187, L-189, L-194, L-201.
- **applied:** L-187 — evidence write nằm trên đường trả kết quả và lỗi ghi không bị nuốt; L-189 — mock được gắn nhãn ngoại tuyến, không claim live; L-194 — adapter không tự phân loại lại policy, broker quyết admission; L-201 — test xuyên request/hash/decision/forward/evidence; L-163/L-165 — giữ oracle block/timeout/invalid riêng và chạy lại toàn suite sau lỗi tương thích SDK.
- **ignored:** Không bỏ qua lesson đã truy hồi; các chi tiết mutation-kill của L-165 không áp dụng vì gate không chạy mutation testing.
- **fallback:** Script recall không khởi động được do `python3`, `py`, `python` không nằm trong PATH; đã dùng đường dự phòng đọc trực tiếp `LESSONS_LEDGER_v0.md` theo protocol.

## OPERATING_MAP_CONSULTED

- Lane: B-INFRA / governance runtime tại tầng T4; phục vụ adapter cho agent, không mở lane mới và không đè lên các mảnh đang bị chôn.
- Phụ thuộc: protocol frame hiện có, broker daemon ở deployment, evidence schema và MCP SDK.
- Ranh giới: đây là example/integration readiness ngoại tuyến, không phải live acceptance hoặc authority mới.

## CORE_FILTER_APPLIED

1. **Lane/track:** B-INFRA — governance kernel adapter.
2. **Tọa độ:** T4 runtime/governance, M3 OSS example.
3. **Kết tủa:** template adapter tái dùng + integration tests + evidence manifest.
4. **Bất biến:** broker-first, fail-closed, evidence-to-disk, secretless; không tự cấp quyền.
5. **Risk:** ORANGE vì chạm security/admission integration nhưng chỉ build ngoại tuyến, không production impact.

## EVIDENCE-ON-CLOSE

- `examples/codex-cli/codex_adapter.py` — `d7a8b23e60facf8d9162fc1491f2d099d52279b279180ab965e72f19e4205cc7`
- `examples/codex-cli/test_codex_adapter.py` — `0d34b91f3d47ff1dba2f65e0a7f00d5f61b452e62f483285a387995013bcf056`
- `examples/codex-cli/README.md` — `7b69aacc522e62c4e13efec99d2e89f743b547aff4f192d61aa4729df6826662`
- `examples/claude-code/claude_code_mcp_adapter.py` — `481a84128838acb90951a8a495fdf66a46ec2a8930c54b2f4e717e92511be87f`
- `examples/claude-code/test_claude_code_adapter.py` — `8025768fc51667c9e481b00952c31af294fbd894ccd77cf856654d68a2ac6e6c`
- `examples/claude-code/README.md` — `ab9b52e701da778a2378ee7949ff53741d8f6f680fe1312e09a4d61bc4e3fbaf`
- `examples/ADAPTER_BUILD_GATE.md` — `e97f7d7bb537fc1d0c9691eb0d71d3bc035b0fe66080d02c7b7e6b1864dfb847`
- `decision_memory/GENOME_BUILD_ROADMAP_v0.md` — `0c716c5e8e7a21731c9e076191c0a0f4dced7db11c150d866fb7f4751c2475d5`

## LESSON_HARVESTED

`NO_LESSON_THIS_GATE:` Không phát hiện bất biến kiến trúc mới đủ độ chín để ghi thêm vào L5; gate áp dụng các lesson đã có. Sai khác MCP 2.2/Pydantic được khóa bằng nhánh tương thích và regression test ngay trong artifact, chưa nên nâng thành lesson toàn công ty.

## KIỂM TRA ĐÓNG GATE

- Lesson drift: `CLEAN` — sổ bài học không lệch.
- Enforcer: `PASS` — pre-check sạch trên `examples/ADAPTER_BUILD_GATE.md`; đây chỉ là kiểm tra phạm vi, không tự cấp authority mới.
- CORE/COMPASS: không thay đổi CORE; hash CORE vẫn khớp COMPASS, NEXT_D giữ `CORE-D170`.
