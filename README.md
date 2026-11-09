# 九城市行政边界与 1 km 空间网格

## 1. 数据概览

研究覆盖中国、美国、英国共九座城市，**以完整行政边界作为研究范围**，不基于人口密度、建成区或都市圈范围做额外裁剪。

| 国家 | 城市 | 城市代码 | 采用的行政边界范围 | 原始数据来源 |
|---|---|---|---|---|
| 中国 | 北京 Beijing | `BJ` | 北京市（省级直辖市） | GADM v4.1，Level 1 |
| 中国 | 成都 Chengdu | `CD` | 成都市（地级行政区） | GADM v4.1，Level 2 |
| 中国 | 上海 Shanghai | `SH` | 上海市（省级直辖市） | GADM v4.1，Level 1 |
| 中国 | 深圳 Shenzhen | `SZ` | 深圳市（地级行政区） | GADM v4.1，Level 2 |
| 美国 | 纽约 New York City | `NYC` | New York City，五个 borough | U.S. Census TIGER/Line 2026，PLACE |
| 美国 | 芝加哥 Chicago | `CHI` | City of Chicago | U.S. Census TIGER/Line 2026，PLACE |
| 美国 | 旧金山 San Francisco | `SF` | City of San Francisco | U.S. Census TIGER/Line 2026，PLACE |
| 英国 | 伦敦 London | `LON` | Greater London（大伦敦） | Greater London Authority（GLA） |
| 英国 | 曼彻斯特 Manchester | `MAN` | City of Manchester（曼彻斯特市） | Office for National Statistics（ONS）2026 年 5 月 LAD |

**范围定义**：`NYC` 包含五个 borough；`LON` 为 Greater London，而非面积很小的 City of London；`MAN` 为 City of Manchester，**不是** Greater Manchester。由于各国行政体系不同，以上边界不表示完全等价的行政层级。

## 2. 原始数据来源

| 数据 | 下载 / 文档 | 用途及版本备注 |
|---|---|---|
| GADM | https://gadm.org/download | v4.1；中国省级和地市级行政边界 |
| U.S. Census TIGER/Line | https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html | 2026 年 PLACE；法定边界参考日期为 2026-01-01 |
| Greater London Authority | https://data.london.gov.uk/dataset/statistical-gis-boundary-files-for-london-20od9 | Greater London boundary；实际边界年份以原始数据元信息为准 |
| ONS Local Authority Districts | https://www.data.gov.uk/dataset/1676926f-6c2f-431b-83c0-c08c8e2ae44f/local-authority-districts-may-2026-boundaries-uk-bfe | May 2026 UK LAD boundaries，选择 Manchester |
| EPSG:6933 | https://epsg.io/6933 | 统一网格使用的全球等面积投影 |

**边界年份不完全一致**：美国数据采用 2026 版、ONS 为 2026 年 5 月版本；GADM v4.1 和 GLA 下载产品须分别记录其来源及实际更新时点。因此，本研究采用**来源版本固定（version-frozen）**的边界策略，而不宣称九城均为同一年法定边界。建议在 `metadata/` 中另存下载日期、下载地址、源文件 SHA-256 和源数据许可信息。

## 3. 统一空间网格协议

| 属性 | 规范 |
|---|---|
| 目标空间单元 | 规则投影方格，`1000 m × 1000 m` |
| 网格 CRS | `EPSG:6933`（WGS 84 / NSIDC EASE-Grid 2.0 Global） |
| 固定网格原点 | `(x₀, y₀) = (0, 0)`（投影米制坐标） |
| 网格索引 | `grid_col = floor(x / 1000)`、`grid_row = floor(y / 1000)` |
| 保留规则 | 方格与城市行政边界的**面相交面积 > 1e-6 m²**；仅点接触或线接触不保留 |
| 模型空间索引 | `full` 完整方格 |
| 城市范围内统计 | `clipped` 行政边界裁剪方格 |
| 存储格式 | GeoPackage（`.gpkg`） |

**坐标说明**：在 `EPSG:6933` 中，每个 `full` 方格的**投影面积**为 `1,000,000 m²`。由于投影变形，不能将其理解为每处地面实际东西、南北边长都严格为 1000 米。本项目使用自定义 `(0,0)` 原点的 1000 米网格，**不是** NSIDC 发布的官方 EASE-Grid 栅格产品。

### 三类网格图层

- **`all`**：覆盖城市行政边界外接矩形的全部候选方格。仅用于生成过程追溯、调试与验证；城市外方格 `region_id` 可以为空。
- **`full`**：与城市边界具有正面积交集的完整正方形。作为跨模态表征学习的主要 `region_id` 索引；城市边缘方格可能超出行政界线。
- **`clipped`**：将同一组 `full` 方格与城市边界求交后得到的面。用于按行政范围统计 POI、道路、建筑和土地利用等要素。

在每一座城市内，`full` 和 `clipped` 的网格条数与 `region_id` 集合应完全一致。**不要将 `clipped` 当作等面积完整方格。**

## 4. 数据处理流程

1. **选择边界**：从上述来源提取每座城市的完整行政边界，导出为 GeoPackage。
2. **统一坐标**：使用 QGIS 将边界正确重投影到 `EPSG:6933`（不能仅修改 CRS 标签）。
3. **修复几何**：使用 *Fix Geometries* 清理无效几何。
4. **融合边界**：使用 *Dissolve*，不设置融合字段，且不勾选 *Keep disjoint features separate*，将城市范围融合为单个 MultiPolygon 要素。
5. **构建固定原点网格**：沿 `EPSG:6933` 的 1000 米整数倍坐标生成不重叠方格，而不是从各城市外接矩形的任意左下角开始生成。
6. **筛选有效城市网格**：保留与行政边界具有正面积交集的完整方格。
7. **生成裁剪网格**：计算格网与行政边界的几何交集，并统计其面积及覆盖率。
8. **分配编号、保存 QA 报告**：生成 `region_id`、`global_grid_id` 及面积等字段，并检查重复格网和面积守恒情况。

若使用配套 PyQGIS 脚本 `scripts/urbantransferbench_grid_1km_qgis.py`，请在 **QGIS Python 控制台**中执行（而非普通 Python 解释器），设置 `ROOT` 与 `RUN_CITIES` 后运行。脚本可以从每城原始 GeoPackage 自动融合、构建并导出网格；**无需再将手动融合后的文件作为脚本输入**。

## 5. 推荐仓库目录

```text
UrbanTransferBench/
├── README.md                      # 本说明
├── scripts/
│   └── urbantransferbench_grid_1km_qgis.py
├── boundaries/
│   └── raw_admin/                    # 许可允许时提供；否则由使用者自行下载
│       ├── BJ_boundary.gpkg
│       ├── CD_boundary.gpkg
│       ├── SH_boundary.gpkg
│       ├── SZ_boundary.gpkg
│       ├── NYC_boundary.gpkg
│       ├── CHI_boundary.gpkg
│       ├── SF_boundary.gpkg
│       ├── LON_boundary.gpkg
│       └── MAN_boundary.gpkg
└── grid_1km/                         # 生成后的空间数据；按授权情况发布
    ├── all/
    │   └── {CITY}_grid_1km_all.gpkg
    ├── full/
    │   └── {CITY}_grid_1km_full.gpkg
    ├── clipped/
    │   └── {CITY}_grid_1km_clipped.gpkg
    └── metadata/
        ├── grid_definition.json
        ├── {CITY}_grid_qa.json
        └── cities_grid_summary.csv
```

`{CITY}` 代表 `BJ`、`CD`、`SH`、`SZ`、`NYC`、`CHI`、`SF`、`LON`、`MAN` 之一。目录展示的是**推荐组织结构及脚本输出约定**；请以实际提交的文件为准，不要将尚未上传的文件描述为已公开发布。

## 6. 字段字典

以下字段对应配套网格生成脚本的输出表结构：

| 字段名 | 类型 | 含义 |
|---|---|---|
| `region_id` | String | 城市内部区域编号，如 `BJ_000001`；仅城市有效格有值 |
| `city_id` | String | 城市代码，如 `BJ` |
| `global_grid_id` | String | 全球固定网格编号，如 `R4704_C11149`（数值仅为示例） |
| `grid_row` | Integer | EPSG:6933 固定网格的全局行号 |
| `grid_col` | Integer | EPSG:6933 固定网格的全局列号 |
| `center_x` | Double | 完整方格中心投影 X 坐标，单位米 |
| `center_y` | Double | 完整方格中心投影 Y 坐标，单位米 |
| `center_lon` | Double | 完整方格中心 WGS 84 经度 |
| `center_lat` | Double | 完整方格中心 WGS 84 纬度 |
| `full_area_m2` | Double | 完整方格的投影面积，固定为 `1000000` |
| `area_in_city_m2` | Double | 方格与行政边界的交集面积，单位 m² |
| `city_cover_ratio` | Double | `area_in_city_m2 / full_area_m2`，范围 `[0,1]` |

**稳定性提示**：在相同边界数据和脚本版本下，`region_id` 可复现；如果边界更新或网格保留条件改变，城市内的顺序编号可能发生变化。`global_grid_id`（或 `grid_row, grid_col`）才是更稳定的固定原点空间定位键。跨版本关联时请同时保存边界版本。

## 7. 质量控制与复现

各城市建议至少检查以下项目，并在 `grid_1km/metadata/{CITY}_grid_qa.json` 中保存结果：

- `full` 中 `(grid_row, grid_col)`、`region_id` 均唯一；`full` 和 `clipped` 的 `region_id` 集合相等。
- 每个 `full` 要素在投影坐标中的面积约为 `1,000,000 m²`。
- 每个有效网格 `0 < area_in_city_m2 ≤ 1,000,000`，且 `city_cover_ratio` 在 `(0,1]`。
- `sum(area_in_city_m2)` 与修复、融合后的城市行政边界面积基本一致。
- 所有文件 CRS、来源版本、代码和处理参数均有记录。

面积守恒相对误差定义为：

```text
relative_area_conservation_error =
    abs(sum_clipped_area_m2 - boundary_area_m2) / boundary_area_m2
```

实际城市网格数量与误差数值应读取 `cities_grid_summary.csv` 及城市 QA JSON；**本 README 不编造未核验的城市网格数量**。

## 8. 下游数据对齐建议

后续 POI、Road、Building、LandUse、Remote Sensing（RS）、Street View（SV）和 Mobility 等数据，应通过统一网格标识与研究区域对齐：

- 点、线、面要素的**行政范围内统计**优先使用 `clipped` 图层。
- 栅格与遥感可按 `full` 的规则窗口取样，同时保存城市掩膜、有效像元数量及覆盖率。
- 对城市边缘网格，报告 `city_cover_ratio`，涉及密度时须明确分母是完整网格面积还是市内有效面积。
- 不要仅因为某一模态缺失就删除主网格；应记录模态可用性掩膜，并在下游实验中统一确定样本子集。
- Mobility 及下游监督标签的时空尺度、覆盖范围和许可条件需要另行说明。

## 9. 已知限制

1. **行政边界不等于建成区**：北京、成都的完整行政辖区中包含较多非建成区；城市间面积及有效网格数量的差异可能很大。
2. **跨国行政口径不完全一致**：Greater London 与 City of Manchester 等边界的行政层级不同；跨城实验结果须结合覆盖范围解释。
3. **边界来源年份不统一**：该数据集不是单一年份全球同步行政边界产品。
4. **边缘网格具有部分覆盖**：`full` 格虽固定为 1 km²，但其内部属于城市行政范围的面积可能很小。
5. **不包含研究标签**：边界网格本身不提供人口、GDP、碳排放、PM2.5、夜光等标签。

## 10. 许可、署名与公开发布注意事项

**本仓库代码的许可证与第三方地理数据许可应分开处理。** 不能因为脚本采用开源许可证，就认定所有行政边界和基于边界制作的数据都可再分发。

- **GADM v4.1（中国四城）**：免费用于学术和其他非商业用途，但未经事先许可**不得重新分发**。在取得明确授权前，**不要公开上传原始 GADM 几何或由其衍生的行政边界/网格空间文件**；可公开获取说明、独立编写的处理代码、参数定义与不含受限几何的质量统计，并让用户自行从官网获取源数据。来源：https://gadm.org/download
- **U.S. Census TIGER/Line（美国三城）**：美国政府开放地理数据；使用时注明 *U.S. Census Bureau, 2026 TIGER/Line Shapefiles*。来源：https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
- **GLA（伦敦）**：London Datastore 页面列出 Open Government Licence，并要求对国家统计和 Ordnance Survey 来源给予指定版权署名。具体措辞参见原数据页：https://data.london.gov.uk/dataset/statistical-gis-boundary-files-for-london-20od9
- **ONS（曼彻斯特）**：ONS 数字边界产品使用 Open Government Licence，但包含 Ordnance Survey 的知识产权和署名要求。参见：https://www.ons.gov.uk/methodology/geography/licences

对 GLA 和 ONS 数据发布的地图及再利用资料，请保留源数据要求的正式版权和来源声明；记录实际源文件所示的年份，不要用本 README 的日期替代。

> **公开发布建议**：先上传 `README.md`、`README_zh.md`、`scripts/` 及不包含受限几何的元数据；需要发布九城 GPKG 时，先逐项检查授权，尤其是 GADM 的再分发限制。

## 11. 引用（Citation）

若使用本项目，请引用对应数据源及后续正式发布的数据集论文。**论文 DOI、作者、仓库 URL 和正式引用条目尚未确定，暂不虚构。** 正式论文发布后可添加 `CITATION.cff`。

## 12. 联系与维护

本 README 描述当前九城行政边界和统一网格协议。请通过 GitHub Issues 反馈城市范围、几何异常、重复网格或源数据更新问题。
