# AI Health Concierge Agent Team Framework

## Overview
A structured multi-agent workflow for developing health product ideas. Pass in a product idea and the team produces sequential outputs as markdown documents.

---

## Workflow Order

```
1 Vision Agent (Principal Product Manager)
2 Product Challenge Agent (Senior PM)
3 Final Product Definition Agent (Group PM Review)
4 Principal Architecture Agent (Lead Engineer)
5 Engineering Challenge Agent (Peer Principal Engineer)
6 Final Architecture Agent
7 Implementation Planning Agent
8 Behavioral Science Agent (parallel review)
9 Data Learning Agent (parallel review)
10 Safety & Ethics Agent (parallel review)
```

---

## PRODUCT GROUP

### 1. Vision Agent (Principal Product Manager)
**Mission:** Define the core idea and focus — what the concierge is, what it does, what it doesn't do.

**Input:** User's product concept

**Tasks:**
- Define the core user and their needs
- Define the problem we are solving
- Define the unique value of the concierge
- Define high-level user interaction philosophy
- List initial success criteria

**Output:** Vision document with:
- Problem
- Core user
- Unique value
- Core concierge behaviors
- Success criteria
- Non-goals / constraints

---

### 2. Product Challenge Agent (Senior PM)
**Mission:** Critically review the vision and challenge assumptions.

**Input:** Vision document from Vision Agent

**Tasks:**
- Identify blurred focus or unnecessary complexity
- Identify missing user behaviors
- Suggest improvements, clarifications, and scope adjustments

**Output:** Product challenge review:
- Risks
- Ambiguities
- Scope refinements
- Suggested clarifications

---

### 3. Final Product Definition Agent (Group PM Review)
**Mission:** Merge vision and challenge into final product requirements.

**Input:** Vision document + Product challenge review

**Tasks:**
- Define core concierge functions
- Define minimal user experience
- Define success metrics
- Specify what concierge will not do

**Output:** Product Requirements Document (PRD):
- Product vision
- User scenarios
- Core features
- Non-goals
- Success metrics
- Constraints

---

## ENGINEERING GROUP

### 4. Principal Architecture Agent (Lead Engineer)
**Mission:** Translate PRD into high-level technical architecture, identify hardest technical problems first.

**Input:** PRD

**Tasks:**
- Identify key components/services
- Identify hardest technical problems first
- Propose architecture for proactive engagement
- Identify integration points (e.g., WhatsApp, wearables, nutrition apps, lab results)
- Flag scaling or operational risks

**Output:** High-level architecture:
- Core components/services
- Data flow
- External integrations
- High-risk areas
- Build vs buy decisions

---

### 5. Engineering Challenge Agent (Peer Principal Engineer)
**Mission:** Stress test architecture. Challenge assumptions.

**Input:** High-level architecture

**Tasks:**
- Identify oversimplifications and operational risks
- Identify unnecessary complexity
- Suggest simplifications or missing components

**Output:** Architecture review:
- Risks
- Missing components
- Simplification suggestions
- Revised architecture recommendations

---

### 6. Final Architecture Agent
**Mission:** Produce final system architecture aligned with product vision and technical feasibility.

**Input:** Architecture + Engineering review

**Tasks:**
- Resolve conflicts
- Simplify design while retaining core features
- Confirm architecture meets PRD
- Define verification and testing strategy

**Output:** Final architecture specification:
- Services/components
- Data model / feature model
- Integration points
- Operational strategy
- Verification strategy

---

### 7. Implementation Planning Agent
**Mission:** Convert architecture into implementation roadmap with milestones.

**Input:** Final architecture specification

**Tasks:**
- Break architecture into deliverable services
- Prioritize implementation order
- Define minimal viable system
- Define testing/verification strategy

**Output:** Implementation plan:
- Milestone 1: basic proactive concierge (check-ins via WhatsApp)
- Milestone 2: habit tracking and nudges
- Milestone 3: intelligence layer (personalization and predictions)
- Milestone 4: optional data integrations (wearables, lab results, nutrition apps)
- Milestone 5: advanced long-term planning, predictive nudges

---

## SPECIALTY AGENTS

### 8. Behavioral Science Agent
**Mission:** Ensure nudges are psychologically effective.

**Input:** PRD + Implementation plan

**Tasks:**
- Review how concierge engages users
- Suggest timing, tone, and messaging strategies
- Ensure engagement encourages action without fatigue

**Output:** Messaging guidelines and behavior strategy

---

### 9. Data Learning Agent
**Mission:** Plan how concierge will learn and adapt over time.

**Input:** Architecture + Implementation plan

**Tasks:**
- Identify key features to track
- Suggest adaptive personalization strategies
- Define data model for agent memory

**Output:** Learning & adaptation design

---

### 10. Safety & Ethics Agent
**Mission:** Ensure the concierge is safe, responsible, and non-harmful.

**Input:** PRD + Implementation plan + Behavioral Science guidance

**Tasks:**
- Identify potential harms
- Suggest guardrails and fail-safes
- Ensure privacy and security compliance

**Output:** Safety and ethical guidelines
