# 湖表压实台（cc-compact-lab）

CC_Codex 二期数据工程产品线：Tornado + 原生 JS 时间轴 SPA + SQLite。

## 主链

1. 小文件清单：登记湖区碎文件与体积
2. 压实计划：把碎文件编入计划
3. 重写合并：执行合并任务并回写状态
4. 体积对账：计划前后体积对照报告
5. 台参数：现行压实阈值与阈值说明

## 阈值闸（第十一号：闸失效补洞）

合并入口只有一条轨：**闸检凭证 + 被拒件**，不再有「只改提示不拦件」的半修。

- 启动合并时，闸检在 `BEGIN IMMEDIATE` 写事务内执行，与落库同一事务；
  两名仓管并发点合并由 SQLite 写锁串行化，闸检凭证不会被双写覆盖。
- 低于台参数阈值（`compact_threshold_kb`）的碎件写入 `gate_rejections`，
  并给出原因；只有合格件进入合并队列。
- 闸检结果写入只增不改的 `gate_checks` 凭证：芯片、阈值、合格/被拒件
  一次落库，四屏（清单 / 计划 / 合并 / 台参数）读同一份凭证。
- 调低阈值后重跑若已放行，旧拒绝不再挂在计划上——摘要按最近一次闸检
  绑定被拒件，芯片与拒件不会两张皮。
- 体积对账按「挂载体积 − 闸检被拒体积」比对，被拒件单列，不再误报
  「体积不一致」。

对应接口：`GET /api/plans/<id>/gate`、`GET /api/gate_bypass/dash`。
测试：`tests/test_gate_bypass.py`（低阈全拒、混合拦截、并发单写、阈值联动）。

默认账号 `admin` / `123456`，端口 `7300`。

## 预留切口（出题用，基线先通）

- 计划与清单体积同源
- 合并失败半态 / 重跑
- 对账快照与现行体积

## 本地

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
python run.py
```
