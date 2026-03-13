# Smoke 小样本与脏数据复核说明

## 本次结果
- 已生成 smoke 小样本：`benchmark/datasets/smoke/case_eval_smoke.jsonl`
- 已更新种子集：`benchmark/datasets/case_eval_seed.jsonl`
- 已更新复核集：`benchmark/datasets/case_eval_review.jsonl`
- 已更新拒绝集：`benchmark/datasets/case_eval_rejected.jsonl`
- 已更新清洗摘要：`benchmark/reports/dataset_cleaning_summary.md`
- 已更新 smoke 摘要：`benchmark/reports/smoke_build_summary.md`

## 清洗后数据规模
- 总记录：`2491`
- 接受样本：`2081`
- 待复核：`320`
- 拒绝：`90`

## Smoke 集规模
- 总数：`28`
- violation：`16`
- compliant：`12`

## Smoke 集覆盖
- 来源 `违规样本3`：`14`
- 来源 `badcase`：`12`
- 来源 `违规样本2`：`2`

## Smoke 集类别覆盖
- `false_positive_regression`：`10`
- `comparison_or_absolute`：`5`
- `financial_product_confusion`：`5`
- `responsibility_exaggeration`：`2`
- `guaranteed_return`：`2`
- `gifts_or_extra_benefits`：`2`
- `agent_title_or_recruitment`：`2`
- `national_or_regulatory_endorsement`：`2`
- `tax_or_law_misinterpretation`：`2`
- `policy_loan_or_cash_value`：`1`
- `transfer_or_inheritance`：`1`

## 这次复核做了什么
- 补了更多违规原因到轻量类别的映射规则，减少纯人工 review 数量。
- 对合规样本增加了“高风险但无提示语”“金融营销风格过重”“超长文本”筛选。
- 清理了 Excel 文本里的 Unicode 分隔符，保证导出的 JSONL 可被常规逐行解析。

## 当前残留脏数据判断
- `category_not_mapped`：`280`
- `compliant_sample_high_risk_without_disclaimer`：`38`
- `compliant_sample_financial_marketing_style`：`15`
- `text_too_long`：`2`
- `compliant_sample_too_long_for_seed`：`2`

## 残留复核集的结论
- `category_not_mapped` 仍然是主因。这批数据大多不是“是否违规”本身难判，而是标注语言偏编辑意见、品牌话术建议、措辞修订或泛化宣传建议，暂时不适合直接进入评测真值集。
- `compliant_sample_high_risk_without_disclaimer` 和 `compliant_sample_financial_marketing_style` 主要集中在合规样本里，但文本本身带明显销售/对比/财富规划导向，没有足够免责声明，不应直接进入 compliant seed。
- 超长样本暂时保留在 review，更适合后续拆分后再入库，不适合当前轻量 smoke。

## 残留样本示例
### category_not_mapped
- `违规样本2_0007` | `违规样本2` | `配置保险应量力而行，根据自己的实际经济状况选择投保，并非”没钱都要买“` | `有人说：都没有钱吃饭，哪来的钱买保险？我说，正是因为没有钱才更需要买保险。有钱人生个病，花点医疗费九牛一毛，不伤筋动骨，一切正常，家人不受太`
- `违规样本2_0042` | `违规样本2` | `寿险给付保险金的条件之一是死亡，如何准备教育金；不能用专款专用形容保险；每年2万是保费还是什么，要说` | `我们容易高估自律的能力。却又容易低估执行的难度。比如说给自己准备一笔养老钱。谁能保证从现在直到退休前，你能每个月拿出来一笔钱？花钱太容易了。`
- `违规样本2_0046` | `违规样本2` | `”专款专用"建议删除` | `退休规划常见的四大误区之三 / 全心投资子女，忽略自己？ / 不少父母对子女有求必应，应帮尽帮。 / 不过，如果把退休储备金全部用来资助子女`
- `违规样本2_0047` | `违规样本2` | `“而富士了孩子的健康守护" 错字需要修改` | `大多数的父母都是望子成龙，望女成凤，不想让孩子输在起跑线上，更多关注到孩子的教育问题，而富士了孩子的健康守护。打个比方，如果把孩子比作一棵小`
- `违规样本2_0057` | `违规样本2` | `1，”不计算风险发生的概率，而计算风险发生的后果。“如何得出“航空公司不计算风险发生的概率”的结论？` | `很多人都做过飞机，也知道飞机是这个世界上最安全的交通工具之一。虽然飞机失事的概率很低，但是航空公司的风险防范却是极其严格的，到机场之后，再登`

### compliant_sample_high_risk_without_disclaimer
- `合规样本_0008` | `合规样本` | `` | `为了给70岁的母亲设计一个合理的财富传承计划，我们需要首先了解她的家庭情况、财务状况以及资产配置情况，然后根据她的需求和目标，制定相应的传承`
- `合规样本_0013` | `合规样本` | `` | `针对客户30岁女性想购买品质晚年金的问题，建议客户根据自身需求和经济条件来选择。以下是对两种产品的对比，供客户参考： /  / 颐享延年： `
- `合规样本_0015` | `合规样本` | `` | `首先，您需要理解您老公的顾虑。他可能担心购买年金险会加重他的经济负担，尤其是如果他认为医疗险已经足够满足他们的保障需求。您可以通过以下方式来`
- `合规样本_0017` | `合规样本` | `` | `客户说银行也有类似的产品，让在他那购买，我们可以这样回复： /  / 尊敬的客户，我明白您在考虑购买银行的产品，但我相信我们的产品和服务能够`
- `合规样本_0019` | `合规样本` | `` | `亲爱的伙伴，你好！ /  / 我是和客户这样沟通的： /  / 和客户分享～对于我们家庭的财富来讲一般分三个时期，短期、中期还有长期！ / `

### compliant_sample_financial_marketing_style
- `合规样本_0008` | `合规样本` | `` | `为了给70岁的母亲设计一个合理的财富传承计划，我们需要首先了解她的家庭情况、财务状况以及资产配置情况，然后根据她的需求和目标，制定相应的传承`
- `合规样本_0011` | `合规样本` | `` | `针对客户提出的疑问，我们可以从以下几个方面进行解答： /  / 1. 盛世金越的收益问题：盛世金越是一款增额终身寿险，其特点是保额每年以3%`
- `合规样本_0013` | `合规样本` | `` | `针对客户30岁女性想购买品质晚年金的问题，建议客户根据自身需求和经济条件来选择。以下是对两种产品的对比，供客户参考： /  / 颐享延年： `
- `合规样本_0017` | `合规样本` | `` | `客户说银行也有类似的产品，让在他那购买，我们可以这样回复： /  / 尊敬的客户，我明白您在考虑购买银行的产品，但我相信我们的产品和服务能够`
- `合规样本_0019` | `合规样本` | `` | `亲爱的伙伴，你好！ /  / 我是和客户这样沟通的： /  / 和客户分享～对于我们家庭的财富来讲一般分三个时期，短期、中期还有长期！ / `

## 对 benchmark 的建议
- 当前 `smoke` 集已经足够做链路冒烟、规则回归和结果格式核对。
- 不建议把 320 条 review 样本直接并入种子集，否则会污染评测结论。
- 下一步如果继续清洗，优先把 `category_not_mapped` 再拆成“可结构化违规”与“纯编辑建议/不入评测”两类。
- 如果要提升 smoke 的场景多样性，可以再补 8-12 条来自 `违规样本2` 的短文本 hard cases。

## 接受集类别 Top 12
- `financial_product_confusion`：`592`
- `comparison_or_absolute`：`543`
- `tax_or_law_misinterpretation`：`188`
- `responsibility_exaggeration`：`142`
- `evidence_or_source_required`：`137`
- `guaranteed_return`：`124`
- `brand_or_ip_risk`：`104`
- `transfer_or_inheritance`：`101`
- `agent_title_or_recruitment`：`82`
- `inappropriate_metaphor`：`79`
- `gifts_or_extra_benefits`：`52`
- `pension_term_misuse`：`51`
