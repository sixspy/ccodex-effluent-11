# 污水排放批（effluent）

数据工程母仓：处理厂采样入库 → 超标旁路挂起 → 准排放裁定 → 封批升代 → 排放许可对账。

## 骨架一句话

采样批次入库后裁定超标才准排放封批，驳回进旁路挂起，指标血缘与排放许可对账。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器访问 http://localhost:11600

- 管理账号：`admin` / `admin123`
- 读写账号：`writer` / `writer123`
- 只读账号：`viewer` / `viewer123`

## 本地开发

```powershell
cd projects/14-effluent
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8000
```

## 自测

```powershell
$env:PYTHONPATH="backend"
python -m pytest
python scripts/count_loc.py
```

## effluent-11 回执禁结（2026-11-25 当日锁死）

外送化验空桩回执未到，禁止结案写入正式册：

- 甲路径（默认 formal）：回执列空，`POST /api/releases/complete` 当场 400 拒写，
  正式册/采样完成态/许可配额零改，审计记 `回执禁结偏航`；
- 乙路径（shadow）：无回执只登记影子草稿，回执到达后原子升正、草稿作废；
- 对账完结灯与空桩待回互斥，影子完成不当结案；配额扣减推迟到回执到达；
- 两路会话同批抢完成走批锁，后到 409 且只记争用痕。

拍板全文见 [docs/effluent-11-回执禁结说明.md](docs/effluent-11-回执禁结说明.md)，
三红测试 `tests/test_effluent_11_jia.py` / `_yi.py` / `_zheng.py`，
并发脚本 `tests/ping_complete_lock.py`。
