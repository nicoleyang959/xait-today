# 私密项目库：云端配置与验收

本功能是可选模块。公开日报仍可用 Python 标准库离线构建与阅读；
**默认关闭云收藏**，不需要账号、数据库或 Node.js 才能运行日报。

本页是部署操作说明，不是已经完成部署的证明。若尚未完成以下配置、
真实隔离测试以及电脑／手机实测，保持 `enabled: false`，不得宣称云同步可用。

## 费用、权限与数据边界

- 仅使用 Supabase **Free** 方案。免费额度不足、项目低活跃暂停或网络受限时，
  记录保持待同步，公开日报不受影响。不购买付费套餐，不自动升级或自动保活。
- 项目库不是公开收藏墙。每位 GitHub 登录用户只能读写自己的记录；
  RLS 和服务端所有权检查是隐私边界，而不是按钮是否隐藏。
- 笔记、待同步队列、备份和账号会话不进入公开 issue、日报 HTML、Git、
  每日采集器或自动发布输入。不抓取手动链接的网站正文。
- 本功能不宣称端到端加密；托管服务和项目管理员仍具有平台管理权限。
- 除每人最多 1,000 条有效记录外，首版另有两项服务端运行预算：每账号累计
  最多 5,000 个链接身份（含删除墓碑）和 10,000 个操作回执。预算计数与写入
  使用同一账号事务锁；达到任一预算时返回 `storage_limit_reached`，拒绝新的
  写入并保留本地待同步内容。已有回执的重试与读取继续可用；不自动清理回执、
  不删除墓碑，也不让旧离线操作因为过期而再次生效。
- 这些是每账号行数上限，不是对整个 Free 项目容量或无限用户数量的承诺。
  多账号、索引、Auth 与数据库维护仍消耗共享额度。出现容量错误时保留队列，
  先导出备份并由你与使用者明确安排迁移／维护；不要静默重置账号、破坏幂等记录
  或升级付费。运行预算耗尽后，新建、编辑、删除与恢复均可能暂时无法同步。

## 1. 由你本人创建云项目

1. 在 Supabase 控制台注册／登录，并由你本人确认服务条款。
2. 新建一个空的 Free 项目，例如 `xait-today-records`，使用控制台推荐区域。
   若没有可用免费项目名额，停止；不要擅自改用付费方案。
3. 数据库访问秘密及后续 OAuth secret 只在服务端控制台填写。
   不读取、不复制到对话，不写入项目文件、终端输出、截图或测试 fixture。
4. 此时不要公开启用收藏入口。

## 2. 应用数据库迁移并完成隔离测试

在这个**新建且未开放给真实读者的项目**的 SQL Editor 中，依次运行：

1. `supabase/migrations/202610270001_private_project_library.sql`
2. `supabase/tests/private_project_library.sql`

迁移只创建 `xait_private` 命名空间与两个公开 RPC，不替换既有表或历史数据。
迁移应只应用一次；已应用后不要通过删除真实表来“重跑”。

测试脚本使用两个明确的合成身份、合成项目及临时断言函数，整个事务最后
`ROLLBACK`。若合成身份 ID 已存在，脚本会拒绝运行，避免复用真实数据。
仅在受控测试项目中执行，不能拿真实用户的记录做隔离测试。

成功时应看到 `PRIVATE_LIBRARY_SQL_TESTS_PASSED`，最后事务回滚。覆盖：

- 匿名拒绝、未登录拒绝、读者 A／B 隔离、伪造所有者和直接表写入拒绝；
- 相同操作 ID 幂等、同 ID 不同请求拒绝、同 URL 不覆盖已有笔记；
- 版本冲突、删除正文及跟进状态清除、墓碑同步、旧离线编辑不能复活删除记录；
- 显式恢复、每用户 1,000 条有效记录、5,000 字笔记及 URL 边界；
- 5,000 个累计身份和 10,000 个永久回执上限、预算耗尽后旧重试仍然幂等、
  不存在的记录请求不会产生回执、预算拒绝不修改已有记录。

仓库的 `tests/test_records_backend.py` 只验证离线 SQL 合约和防回归结构，
**不能替代真正执行上述 SQL 隔离测试**。无 PostgreSQL 或云项目时可以完成
代码验证，但必须保留真实后端验收为未完成。

## 3. 由你本人配置 GitHub OAuth

1. Supabase → Authentication → Sign In / Providers → GitHub，取得该项目的
  官方 Callback URL。形状为 `https://<project-ref>.supabase.co/auth/v1/callback`。
2. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App。
   Homepage URL 使用正式网站首页；Authorization callback URL 使用上一步
   Supabase 提供的完整地址。不要启用 Device Flow。
3. 由你本人创建并将 Client ID／Client secret 填入 Supabase GitHub Provider。
   不需要在网页或仓库里保存 OAuth secret。若授权提出仓库读写等额外权限，
   先停止并核对，不为收藏功能授予仓库管理权。
4. Supabase → Authentication → URL Configuration：Site URL 和精确的
   Redirect URLs 均设为：

   `https://nicoleyang959.github.io/xait-today/`

   生产环境不填写 `*` 或 `**`。GitHub 登录使用 PKCE，登录完成统一回首页，
   客户端交换认证 code 后立即清理地址栏认证参数，并恢复收藏意图或阅读位置。
5. 只启用 GitHub 登录。不要启用匿名登录，不增加收集私密信息的 OAuth scope。

正式配置的云库仅供正式实例使用。fork／clone 用户应使用自己的项目及正式
站点地址，不能默认连接作者的云库。普通 HTTP 局域网阅读不启用登录。

## 4. 先保持关闭，准备公开配置

公开配置输入为 `site/cloud-records.json`，只有四个字段：

- `enabled`：布尔值，未配置时为 `false`，另外三个值必须均为空字符串。
- `supabaseUrl`：该项目唯一的 HTTPS Supabase origin，不带路径或查询。
- `publishableKey`：控制台提供的新的 `sb_publishable_…` 公共客户端标识。
- `redirectUrl`：正式网站首页的完整 HTTPS 地址。

配置校验不会接受“`enabled: false` 但偷偷保留其他非空字段”的半配置状态。
在准备正式上线前，将公开字段保存在你自己控制的位置，不要填入关闭配置。
需要真实登录预发布验收时，仅在受控的 HTTPS 预发布实例中使用启用配置，并为
该预发布首页单独配置精确回调；不能放宽正式实例的 origin guard 或以普通
HTTP 局域网地址代替。预发布验收不等于正式上线。

publishable key 可以公开，但不授予他人的数据访问权；所有权限由 RLS 和 RPC
的 `auth.uid()` 检查决定。不要填写 secret key、legacy service-role／anon JWT、
access token、refresh token 或其他服务器凭据。公开构建对错误类型或错误位置
的配置应拒绝，不因字段名字看起来安全就放行。

不要通过放宽整个 CSP 或关闭敏感扫描解决配置问题。启用后仅允许连接本项目
的唯一 HTTPS origin，不依赖外部 CDN、泛域名或 `unsafe-eval`。

## 5. 电脑与手机真实验收后再上线

1. 同一个 GitHub 账号在电脑和手机正常完成登录。保存一个合成测试项目，
   更改笔记和状态，确认另一台设备自动出现相同内容。
2. 断网后保存与编辑，刷新后仍保留本地内容；恢复网络后只同步一次。
   “已存本地／待同步”不能冒充“已同步云端”。
3. 两台设备同时编辑，确认提示冲突并保留两份内容，而不是按设备时间覆盖。
4. 删除后用另一台设备的旧草稿同步，确认不会复活；重新收藏须明确恢复。
5. 切换账号不展示旧账号的数据，旧请求和旧队列不进入新账号；待同步内容退出前
   可先同步、导出或取消。授权失效、配额不足和存储禁用均有明确错误状态。
6. 七套主题、移动端键盘、焦点、中英文、JSON 导入导出与 Markdown 导出通过。
   笔记始终是原始纯文本，不进入译文目录或公开页面源码。
7. 运行公开测试与确定性构建，确认 Git 提交只含精确的源码及静态产物白名单。
8. 只有上述隔离测试、真实双设备测试和安全检查均通过后，才将正式配置切为
   `enabled: true`，按现有快进发布流程部署并核对线上文件。

真实授权和双设备步骤需要你本人参与；不能用模拟测试的通过替代这些证据。

## RPC 合约（客户端开发）

- `list_my_records(p_account_id, p_after_id, p_limit)`：每页 1–100 项，返回
  `{records, next_after}`，按 UUID 排序；包含内容已清除的删除墓碑。
- `apply_record_mutation(p_account_id, p_mutation_id, p_record_id, p_operation,
  p_expected_version, p_payload)`：操作为 `create/update/delete/restore`，返回
  `{status, record, applied_version}`；状态为 `applied/existing/conflict/deleted`。
  `applied_version` 固定为该次操作最初返回的版本，`record` 为当前版本。
  丢失应答后重试若发现当前版本更高，后续本地编辑必须进入冲突，不能静默覆盖。
- 请求不接受所有者、服务端版本或时间。所有者来自 `auth.uid()`；记录身份在
  服务端由保守规范化的 URL 计算。相同名称不会被猜测合并。
- `p_account_id` 是本地队列固定的预期账号，不是所有者赋值；两个 RPC 均在任何
  数据读写之前核对其与 `auth.uid()` 一致。浏览器多标签页切换账号时，旧账号
  队列即使携带了新会话，也只能得到 `account_changed`，不能写入新账号。
- 可写正文仅为 `url/title/source_id/source_issue_date/notes/status`；可选
  `canonical_url` 仅在与服务端结果相同时接受。更新时建议只发送笔记／状态／标题。
- `source_id` 为 `manual`、四个 GitHub／Product Hunt 项目来源之一或空；
  手动添加不伪造来源期号。删除保留不透明 URL 摘要、ID、版本与必要时间，
  状态固定回到无历史含义的 `to_research` 协议标记，不保留“已体验／重点关注”。
- 不存在或不属于当前账号的记录修改统一返回
  `{status: "deleted", record: null, applied_version: null}`，不创建任何记录或回执。
- 新操作被服务端预算拒绝时 SQLSTATE 为 `P0001`、消息为
  `storage_limit_reached`；客户端不能据此移除本地队列或显示已同步。
  同一个 mutation ID 的已有回执在预算检查前重放，永远不因预算清理而丢失。
