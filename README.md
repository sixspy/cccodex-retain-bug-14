# cc-retain-lab

CC_Codex 二期（26.11）**数据工程**产品线：**留存裁撤台**（FastAPI + 原生 JS SPA + SQLite）。

## 一句话骨架（自有，非外仓抄题）

**分区留存策略版本 → 到期扫描裁决 → 归档或销毁执行 → 策略与实物分区对账**

与现有六线正交（不是采集目录、ETL 管道、同步源、解析入库、编排流、种子摄取）。  
也不碰外仓常见指纹（Feed 归并 / 作业编排 / CDC 游标 / 质检签发 / 贴源-明细-汇总）。

## 领域

- **所属领域**：数据工程  
- **子方向**：数仓与数据湖（分区留存 / 裁撤闭环）

## 技术栈

| 层 | 选型 |
|----|------|
| 后端 | Python 3.12、FastAPI、Uvicorn、SQLite |
| 前端 | 原生 JS 单页（全中文），青灰底 + 铜强调，顶栏导航（非绿侧栏克隆） |
| 测试 | pytest + httpx（本地秒级闭环，优先于 compose） |

## 基线已通主链

1. 现行留存策略（主题域 / 保留天 / 到期动作）  
2. 实物分区列表（在线 / 归档 / 销毁）  
3. 按基准日到期扫描 → 生成待执行裁决  
4. 单条裁决执行（归档写地址 / 销毁清零）  
5. 策略与实物对账报告  

预留切口（未做，供后续功能题）：策略换版生效窗、重裁作废、批量失败闭互斥、跨域依赖冻结、归档回灌等。

## 本地（推荐反馈环）

```powershell
cd claude-workspace\cc-retain-lab
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest
python run.py
```

http://127.0.0.1:6500/login · **admin / 123456**

## Docker

```powershell
docker compose up -d --build
```

端口 **6500**。冒烟：`python ..\scripts\_smoke_lab_access.py --dir .`
