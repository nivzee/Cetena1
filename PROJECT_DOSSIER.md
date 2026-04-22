# Cetena v0.15 - Software Factory Dossier

## 1. Triết lý Triple-Tree (DNA Kernel)
Hệ thống tách biệt hoàn toàn giữa **Mã nguồn (Core)** và **Cấu hình (DNA)**.
- **Entity**: Centana (EID:1), VinGroup (EID:2).
- **Domain**: PUR, FIN, HR, WHS.
- **DNA**: Mapping (EID + DID) -> UI (Màu sắc) & Logic (Rule bóc tách).

## 2. Cấu trúc Database (PostgreSQL)
- dna_kernel: Trung tâm điều phối giao diện và quy tắc.
- standardization_rules: Lưu trữ công thức bóc tách AI.
- roles & users: Phân quyền dựa trên Power Level (100, 50, 10).

## 3. Thành phần Mã nguồn
- web_dashboard.py: Dashboard DNA-Powered.
- standardize_with_ai.py: Engine bóc tách AI Gemini.

## 4. Cơ chế Phân quyền (RBAC)
- Khóa Entity: User chỉ thấy dữ liệu của công ty mình.
- Khóa UI: Menu tự ẩn nếu không đủ quyền.
