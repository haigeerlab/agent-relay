# Capability Map: [填写 Initiative 名称]

> 由 `/spec` 的 Phase 0 产出。**必须经人工评审后才能往下走。**
> Addy 原文：把图搞错代价很大，评审十行不算什么。

## 目标

[1-3 句话：这个 initiative 要解决什么问题、给谁用。]

<!-- 这一段是 Proposal 评审的目标指纹底本（`spec-digest.py` 计算）。
     改写目标会让已发布的 Proposal 被判为过期，所以改了先人工评审；追加模块不需要改这里。
     标题必须是 `## 目标`（或 `## Goal`）—— 指纹脚本按标题定位这一节。 -->

## 模块

| Module id | Responsibility | Depends on |
|---|---|---|
| example-a | 一句话说清这个模块负责什么 | — |
| example-b | ... | example-a |

Build order: example-a → example-b

<!-- Spec Guard 按严格串行推进。为兼容上游格式，逗号分组会按左到右顺序展开为单模块步骤，不代表并行授权。 -->

---

## 评审记录

- [ ] 模块边界确认（砍掉或替换一个模块，不需要重写其他模块的需求）
- [ ] 依赖方向单向无环（互相依赖 = 它们本来就是一个模块）
- [ ] module id 已定稿（kebab-case，之后绝不改名 —— 同一个 id 同时是
      `spec/<id>.md`、`tasks/<id>/`、`.agent/state.json` 的 `activeModule` 和 Proposal 中的模块名，
      已发布的 Proposal 改不动）
- [ ] 构建顺序符合依赖拓扑

评审人：
日期：
