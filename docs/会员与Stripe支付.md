# 极速下 Pro — 会员与 Stripe 支付

## 产品规则

| 项 | 说明 |
|---|---|
| 计费 | Stripe **月度订阅**，到期自动续费；可在 Customer Portal 取消 |
| 登录 | 邮箱 + 密码（JWT httpOnly Cookie） |
| Pro 权益 | **解析无限次 + AI 视频总结无限次** |
| 免费额度 | 每日解析 10 次、AI 总结 10 次（超出需 Pro） |
| 数据 | SQLite（`DATABASE_PATH`，默认 `backend/data/app.db`） |

## 你需要在 Stripe 做的事（测试模式）

1. 注册 [Stripe Dashboard](https://dashboard.stripe.com/register)，保持 **Test mode**
2. Developers → API keys → 复制 `sk_test_...` → `backend/.env` 的 `STRIPE_SECRET_KEY`
3. Product catalog → 创建商品「极速下 Pro」→ Recurring Monthly → 记下 `price_...` → `STRIPE_PRICE_ID`
4. 安装 [Stripe CLI](https://docs.stripe.com/stripe-cli)，执行：

```bash
stripe login
stripe listen --forward-to http://127.0.0.1:8001/api/billing/webhook
```

将 CLI 打印的 `whsec_...` 写入 `STRIPE_WEBHOOK_SECRET`（本地用 CLI 的 secret，不要用 Dashboard 正式 endpoint 的）。

5. 配置 `JWT_SECRET`（足够长的随机串）、`PUBLIC_APP_URL=http://127.0.0.1:5173`
6. Settings → Billing → **Customer portal**：在 Test mode 下启用并保存（否则「管理订阅」可能白屏）
7. 重启后端，再开前端；注册账号 → 升级 Pro → 测试卡 `4242 4242 4242 4242`

**说明：** 本机需能访问 `api.stripe.com`。没有公网域名没关系，用 Stripe CLI 转发 webhook 即可。完全断网无法测真实 Stripe。  
前端开发服务器绑定 `127.0.0.1:5173`（见 `frontend/vite.config.ts`），与 Stripe 回跳地址一致。

## 本地三终端

```bash
# 1 后端
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 2 Stripe webhook 转发
stripe listen --forward-to http://127.0.0.1:8001/api/billing/webhook

# 3 前端
cd frontend
npm run dev
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册并写 Cookie |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户 / VIP 状态 |
| POST | `/api/billing/checkout` | 创建 Checkout Session（需登录） |
| POST | `/api/billing/portal` | Customer Portal（需登录且已有 customer） |
| POST | `/api/billing/webhook` | Stripe webhook（验签 + 事件幂等） |

## 安全要点

- 开通权益 **只信 webhook**，不信前端 success 回跳单独发货
- Webhook 使用 **raw body** + `Stripe-Signature` 验签
- `stripe_events.event_id` 保证同一事件只处理一次
- Checkout 在服务端创建；金额来自 Stripe Price；`metadata.user_id` 绑定用户
- Checkout 使用 Idempotency-Key，降低连点重复开单风险
- 已是 VIP 时拒绝再次 Checkout，引导 Portal

## 验收清单

1. 未登录可解析/总结，各有每日 10 次上限  
2. 注册/登录后 Cookie 保持会话  
3. 配置 Stripe 后，「升级 Pro」跳转 Checkout，测试卡支付成功  
4. CLI 收到 webhook 后，`/api/auth/me` 显示 `is_vip: true`  
5. VIP 解析与总结均不扣次  
6. 「管理订阅」可打开 Portal（需先在 Dashboard 启用 Customer portal）  
7. 篡改 webhook 签名返回 400  

