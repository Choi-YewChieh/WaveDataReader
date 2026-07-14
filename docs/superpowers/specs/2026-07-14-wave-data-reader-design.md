# Wave Data Reader Design

**Date:** 2026-07-14  
**Status:** Approved for planning  
**Goal:** 读取波表文件（txt/csv/arb），输出逗号分隔字符串或带 TMC 头的二进制，用于功能验证与仪器下发验证。

## Context

- 样例：`wave.txt` / `wave.csv` 为逐行浮点明文；`wave.arb` 为二进制波点（样例 4000 字节 ≈ 2000 × int16 LE）。
- 用途：先本地验证读写与格式转换，再把二进制载荷用于仪器下发。

## Approach

采用**单模块流水线**：`read_wave` → 统一 `WaveData` → `to_string()` / `to_binary()`，外加轻量 `demo.py`。

不按格式拆多类 Reader（过度设计）；不做纯一次性脚本（不利于下发复用）。

## Architecture

```
文件路径 (+ 可选参数: bytes_per_point, 波点数据范围)
        │
        ▼
   read_wave()
        │  txt/csv → 解析浮点（约定约在 [-1, 1]）
        │  arb     → 按 bytes_per_point + 波点数据范围解包整数
        │            → 归一化 float ∈ 约 [-1, 1]
        ▼
    WaveData
      - points: list[float]   # 统一约在 [-1, 1]
      - point_count
      - source_path / file_type
        │
        ├── to_string()  → "v0,v1,v2,..."
        └── to_binary(bytes_per_point=2, with_tmc=True, code_range=...)
              │  float → 整数: 按「波点数据范围」量化并钳位
              │  pack little-endian（有符号/无符号随范围）
              └── optional TMC header + payload
```

> **统一量纲：** 内存中波点一律为约 [-1, 1] 的 float。读 arb / 写二进制时按用户选择的**波点数据范围**做码值↔浮点映射，避免对已是 DAC 码的数据二次放大。

### 波点数据范围（`code_range`）

用户可选的波点码值量程（对外用数字区间展示，便于波表算法工程师理解）：

| 波点数据范围 | 码值区间 | 归一化浮点 `v∈[-1,1]` → 码值 | 打包 |
|--------------|----------|------------------------------|------|
| `±32767`（默认） | [-32767, 32767] | `round(v * 32767)`，钳位 ±32767 | 小端有符号 16 位（`<h`） |
| `0~65535` | [0, 65535] | `round((v + 1) / 2 * 65535)`，钳位 0~65535 | 小端无符号 16 位（`<H`） |
| `0~16383` | [0, 16383] | `round((v + 1) / 2 * 16383)`，钳位 0~16383 | 小端无符号 16 位（`<H`，有效 14 位） |

- 读 arb 与写二进制必须使用**同一**波点数据范围，往返才一致。
- 当前三种预设均按 **2 字节/点** 理解；`bytes_per_point` 仍保留，默认 `2`。若 `bytes_per_point≠2` 与上述三种范围组合不支持，应报错（避免 silently 错解）。

### Public API (intended)

```python
wave = read_wave(path, file_type=None, bytes_per_point=2, code_range="±32767")
s = wave.to_string()
payload = wave.to_binary(bytes_per_point=2, with_tmc=True, code_range="±32767")
# code_range 可选: "±32767" | "0~65535" | "0~16383"
```

- `file_type`: 默认由后缀推断（`.txt` / `.csv` / `.arb`）；可显式覆盖。
- `bytes_per_point`（读 arb / 写二进制）：默认 `2`。
- `code_range`（**波点数据范围**）：默认 `"±32767"`；决定 arb 解包与二进制量化方式。

## Input Formats

| 类型 | 规则 |
|------|------|
| txt / csv | 逐行浮点；跳过空行；行内若含逗号则按逗号拆分；非法数字报错并带行号 |
| arb | 整文件为连续整数（有符号/无符号由波点数据范围决定）；长度必须能被 `bytes_per_point` 整除；按所选范围归一化为 float |

## Output Formats

### String

- 英文逗号分隔的十进制文本，无空格（与需求示例一致）。
- 点数与读入一致；内容为归一化后的浮点数值（txt/csv 基本原样；arb 按波点数据范围反推为约 [-1, 1]）。

### Binary + TMC

量化（用于下发）完全由 **波点数据范围** 决定，见上表；超出浮点约 [-1, 1] 时钳位到该范围的码值端点，默认不告警。

TMC 头：

- 形式：`#9` + **9 位十进制点数**（左零填充）+ 二进制载荷  
- 示例：1024 个点 → `#9000001024` + 其后 `1024 * bytes_per_point` 字节  
- 注：9 位数字表示的是**波点数**，不是载荷字节数  
- 点数 ≥ 10^9 时拒绝生成（超出 9 位字段）

`with_tmc=False` 时仅返回量化后的原始二进制载荷。

## Error Handling

| 情况 | 行为 |
|------|------|
| 路径不存在 / 不可读 | 抛异常，信息含路径 |
| 未知扩展名且未传 `file_type` | 抛异常 |
| txt/csv 非法数字 | 抛异常，含行号 |
| arb 长度无法整除 | 抛异常，含长度与 bytes_per_point |
| 不支持的 `bytes_per_point` / `code_range` 组合 | 抛异常 |
| TMC 点数超过 9 位 | 抛异常 |
| 浮点超出约 ±1 | 钳位到当前波点数据范围的码值端点，默认不告警 |

## 运行方式

在项目根目录执行（需 **Python 3.10+**，仅标准库，无额外安装依赖）：

```text
cd "d:\Code Project\WaveDataReader"
```

### 单元测试

```text
python -m unittest test_wave_reader.py -v
```

### Demo CLI（功能验证）

查看参数说明：

```text
python demo.py -h
```

字符串输出（逗号分隔波点，默认预览前 8 点）：

```text
python demo.py wave.txt --out string
python demo.py wave.txt --out string --preview 5
python demo.py wave.csv --out string --save out.txt
python demo.py wave.arb --bytes 2 --out string --preview 5
```

二进制输出（默认带 TMC 头；`--no-tmc` 可关闭）：

```text
python demo.py wave.txt --out binary --tmc --save out.bin
python demo.py wave.arb --bytes 2 --out binary --tmc --save out.bin
python demo.py wave.txt --out binary --no-tmc --save payload.bin
```

波点数据范围（`code_range`，设计目标；默认 `±32767`）：

```text
python demo.py wave.txt --out binary --code-range "±32767" --tmc --save out.bin
python demo.py wave.txt --out binary --code-range "0~65535" --tmc --save out.bin
python demo.py wave.txt --out binary --code-range "0~16383" --tmc --save out.bin
python demo.py wave.arb --bytes 2 --code-range "±32767" --out binary --tmc --save out.bin
```

常用参数：

| 参数 | 说明 |
|------|------|
| `path` | 波表文件路径（`.txt` / `.csv` / `.arb`） |
| `--out string\|binary` | 输出类型，默认 `string` |
| `--bytes` | 单点字节数，默认 `2` |
| `--code-range` | 波点数据范围：`±32767` / `0~65535` / `0~16383` |
| `--tmc` / `--no-tmc` | 二进制是否拼 TMC 头（binary 默认开） |
| `--save` | 写出文件路径 |
| `--preview` | 字符串预览点数，默认 `8` |
| `--file-type` | 强制类型 `txt\|csv\|arb`（可覆盖后缀） |

### 库调用示例

```python
from wave_reader import read_wave

wave = read_wave("wave.txt")
print(wave.point_count)
print(wave.to_string()[:80])
payload = wave.to_binary(bytes_per_point=2, with_tmc=True, code_range="±32767")
# code_range 可选: "±32767" | "0~65535" | "0~16383"
open("out.bin", "wb").write(payload)
```

## Demo Script

`demo.py` 为 CLI 验证入口，命令见上一节「运行方式」。输出：点数、字符串预览或 TMC 头/载荷长度；可选 `--save` 写文件。

## Testing (minimal)


基于仓库样例文件：

1. txt/csv 读入点数与文件一致；字符串前若干点与文件一致。  
2. arb（`bytes_per_point=2`，默认波点数据范围 `±32767`）点数 = 文件大小 / 2。  
3. `to_binary(with_tmc=True)`：以 `#9` 开头；随后 9 位等于点数；载荷长度 = 点数 × 2。  
4. 默认范围下：满幅约 ±1 的点量化后接近 ±32767；arb 往返（读→`to_binary`）应还原为原文件载荷（允许个别 LSB 舍入差，满幅样例应一致）。  
5. `0~65535` / `0~16383`：满幅 `v=±1` 分别映射到范围端点；同一 `code_range` 下读/写往返一致。

## Out of Scope

- 实际 VISA/SCPI 仪器通信（本模块只产出可下发载荷）  
- 大端字节序、任意自定义 `code_min`/`code_max`（仅支持三种波点数据范围预设）  
- GUI  

## Files to Add

| 文件 | 职责 |
|------|------|
| `wave_reader.py` | 读取 + WaveData + 转换 |
| `demo.py` | CLI 验证入口 |
| （可选）`test_wave_reader.py` | 上述最小测试 |

## Success Criteria

- 三种样例均可读取  
- 字符串与带 TMC 的二进制均可生成  
- 二进制载荷可直接用于后续仪器下发验证
