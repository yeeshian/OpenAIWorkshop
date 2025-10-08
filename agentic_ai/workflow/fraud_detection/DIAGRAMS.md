# Fraud Detection Workflow - Visual Diagrams

## Complete Workflow Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SUSPICIOUS ACTIVITY ALERT                             │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Alert ID: ALERT-001                                             │    │
│  │ Customer ID: 1                                                  │    │
│  │ Type: multi_country_login                                       │    │
│  │ Description: Login attempts from USA and Russia within 2 hours  │    │
│  │ Severity: high                                                  │    │
│  └────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────┬──────────────────────────────────────────┘
                                ↓
                    ┌───────────────────────┐
                    │   AlertRouter         │
                    │   Executor            │
                    │                       │
                    │  - Receives alert     │
                    │  - Routes to 3        │
                    │    specialist agents  │
                    └───────────┬───────────┘
                                ↓
         ┌──────────────────────┼──────────────────────┐
         ↓                      ↓                      ↓
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ UsagePattern       │ │ LocationAnalysis   │ │ BillingCharge      │
│ Executor           │ │ Executor           │ │ Executor           │
│                    │ │                    │ │                    │
│ MCP Tools:         │ │ MCP Tools:         │ │ MCP Tools:         │
│ • get_customer_    │ │ • get_customer_    │ │ • get_customer_    │
│   detail           │ │   detail           │ │   detail           │
│ • get_subscription │ │ • get_security_    │ │ • get_billing_     │
│   _detail          │ │   logs             │ │   summary          │
│ • get_data_usage   │ │ • search_          │ │ • get_subscription │
│ • search_          │ │   knowledge_base   │ │   _detail          │
│   knowledge_base   │ │                    │ │ • get_customer_    │
│                    │ │                    │ │   orders           │
│ ↓                  │ │ ↓                  │ │ ↓                  │
│ Risk Score: 0.7    │ │ Risk Score: 0.85   │ │ Risk Score: 0.4    │
│ Indicators:        │ │ Indicators:        │ │ Indicators:        │
│ • Data spike       │ │ • Impossible       │ │ • Normal billing   │
│ • Off-peak usage   │ │   travel           │ │   pattern          │
└─────────┬──────────┘ └─────────┬──────────┘ └─────────┬──────────┘
          └──────────────────────┼──────────────────────┘
                                 ↓
                    ┌────────────────────────┐
                    │ FraudRiskAggregator    │
                    │ Executor (LLM Agent)   │
                    │                        │
                    │ Analyzes all findings  │
                    │ Calculates weighted    │
                    │ risk score             │
                    │                        │
                    │ Overall Risk: 0.65     │
                    │ Level: high            │
                    │ Action: lock_account   │
                    └───────────┬────────────┘
                                ↓
                    ┌───────────────────────┐
                    │   RISK SCORE SWITCH   │
                    │                       │
                    │   Score >= 0.6?       │
                    └───────────┬───────────┘
                                ↓
              ┌─────────────────┴─────────────────┐
              ↓                                   ↓
        (YES - High Risk)                  (NO - Low Risk)
              ↓                                   ↓
┌────────────────────────┐            ┌────────────────────────┐
│ RequestInfoExecutor    │            │ AutoClearExecutor      │
│ (Human-in-the-Loop)    │            │                        │
│                        │            │ Automatically clears   │
│ ┌────────────────────┐ │            │ low-risk alerts        │
│ │ WORKFLOW PAUSED    │ │            │                        │
│ │                    │ │            │ Creates ActionResult:  │
│ │ Checkpoint saved   │ │            │ • action: cleared      │
│ │                    │ │            │ • success: true        │
│ │ Waiting for analyst│ │            └───────────┬────────────┘
│ │ decision...        │ │                        │
│ └────────────────────┘ │                        │
│                        │                        │
│ ┌────────────────────┐ │                        │
│ │ ANALYST REVIEWS    │ │                        │
│ │                    │ │                        │
│ │ Inputs:            │ │                        │
│ │ • Alert details    │ │                        │
│ │ • Risk assessment  │ │                        │
│ │ • All findings     │ │                        │
│ │                    │ │                        │
│ │ Decision:          │ │                        │
│ │ • lock_account     │ │                        │
│ │ • refund_charges   │ │                        │
│ │ • both             │ │                        │
│ │ • clear            │ │                        │
│ └────────────────────┘ │                        │
│                        │                        │
│ Analyst Decision:      │                        │
│ • Action: lock_account │                        │
│ • Notes: "Confirmed    │                        │
│   fraudulent activity" │                        │
└───────────┬────────────┘                        │
            ↓                                     │
┌────────────────────────┐                        │
│ FraudActionExecutor    │                        │
│                        │                        │
│ Executes approved      │                        │
│ action:                │                        │
│ • Lock account         │                        │
│ • Refund charges       │                        │
│ • Both                 │                        │
│ • Clear                │                        │
│                        │                        │
│ Creates ActionResult:  │                        │
│ • action_taken         │                        │
│ • success: true        │                        │
│ • details              │                        │
│ • timestamp            │                        │
└───────────┬────────────┘                        │
            └──────────────┬──────────────────────┘
                           ↓
              ┌────────────────────────┐
              │ FinalNotification      │
              │ Executor               │
              │                        │
              │ • Notify customer      │
              │ • Log audit trail      │
              │ • Close alert          │
              │                        │
              │ Workflow Output:       │
              │ FinalNotification {    │
              │   customer_notified    │
              │   audit_logged         │
              │ }                      │
              └────────────────────────┘
                           ↓
                  ✅ WORKFLOW COMPLETE
```

## Message Flow Sequence

```
1. SuspiciousActivityAlert
   ├─ alert_id: "ALERT-001"
   ├─ customer_id: 1
   ├─ alert_type: "multi_country_login"
   └─ severity: "high"
   
2. Fan-Out (Parallel Execution)
   ├─→ UsageAnalysisResult
   │   ├─ risk_score: 0.7
   │   └─ risk_indicators: ["data_spike", "off_peak_usage"]
   │
   ├─→ LocationAnalysisResult
   │   ├─ risk_score: 0.85
   │   └─ risk_indicators: ["impossible_travel", "high_risk_region"]
   │
   └─→ BillingAnalysisResult
       ├─ risk_score: 0.4
       └─ risk_indicators: ["normal_pattern"]

3. Fan-In (Aggregation)
   → FraudRiskAssessment
     ├─ overall_risk_score: 0.65
     ├─ risk_level: "high"
     ├─ recommended_action: "lock_account"
     └─ reasoning: "Multiple high-risk indicators..."

4. Switch/Case (Conditional Routing)
   IF risk_score >= 0.6:
     → RequestInfoEvent
       └─ Workflow PAUSES ⏸️
       
   ELSE:
     → AutoClear
       └─ ActionResult(action_taken="cleared")

5. Human Input (Analyst Decision)
   → AnalystDecision
     ├─ approved_action: "lock_account"
     └─ analyst_notes: "Confirmed fraudulent activity"
     
   Workflow RESUMES ▶️

6. Action Execution
   → ActionResult
     ├─ action_taken: "lock_account"
     ├─ success: true
     └─ details: "Account locked. Analyst: analyst_001"

7. Final Notification
   → FinalNotification
     ├─ customer_notified: true
     ├─ audit_logged: true
     └─ resolution: "Account locked due to fraudulent activity"

8. Workflow Output
   ✅ Complete
```

## Timing Diagram

```
Time →

0s     AlertRouter
       ↓
1s     ┌──────────────┬──────────────┬──────────────┐
       UsagePattern   Location       Billing
       Executor       Executor       Executor
       ↓              ↓              ↓
       
       [Parallel MCP Tool Calls]
       
12s    ↓              ↓              ↓
       Risk: 0.7      Risk: 0.85     Risk: 0.4
       └──────────────┴──────────────┘
       
13s    FraudRiskAggregator (LLM)
       ↓
       
18s    Risk Assessment: 0.65 (HIGH)
       ↓
       
19s    Switch/Case Routing
       ↓
       
       [HIGH RISK PATH]
       ↓
       
20s    RequestInfoExecutor
       ⏸️  WORKFLOW PAUSED
       
       [WAITING FOR ANALYST...]
       
5m     Analyst Reviews Case
       ↓
       
5m30s  AnalystDecision: lock_account
       ▶️  WORKFLOW RESUMED
       ↓
       
5m31s  FraudActionExecutor
       ↓
       
5m32s  FinalNotificationExecutor
       ↓
       
5m33s  ✅ COMPLETE

Total Active Time: ~33 seconds
Total Wall Time: ~5 minutes 33 seconds (includes analyst review)
```

## State Transitions

```
┌─────────────────┐
│   INITIALIZED   │
│                 │
│ • Workflow built│
│ • Executors     │
│   ready         │
└────────┬────────┘
         ↓
         run_stream()
         ↓
┌─────────────────┐
│    RUNNING      │
│                 │
│ • Processing    │
│   alert         │
│ • Superstep 1   │
└────────┬────────┘
         ↓
         3 specialists complete
         ↓
┌─────────────────┐
│   AGGREGATING   │
│                 │
│ • Fan-in wait   │
│ • LLM analysis  │
│ • Superstep 2   │
└────────┬────────┘
         ↓
         Risk score >= 0.6
         ↓
┌─────────────────┐
│ WAITING_INPUT   │
│                 │
│ • Checkpoint    │
│   saved         │
│ • RequestInfo   │
│   event emitted │
└────────┬────────┘
         ↓
         Analyst decision received
         ↓
┌─────────────────┐
│ EXECUTING       │
│                 │
│ • Fraud action  │
│ • Superstep 3   │
└────────┬────────┘
         ↓
┌─────────────────┐
│  NOTIFYING      │
│                 │
│ • Customer      │
│ • Audit log     │
│ • Superstep 4   │
└────────┬────────┘
         ↓
┌─────────────────┐
│   COMPLETED     │
│                 │
│ • Final output  │
│ • Idle status   │
└─────────────────┘
```

## Checkpoint Structure

```
WorkflowCheckpoint {
  checkpoint_id: "cp_123456789"
  workflow_id: "fraud_detection_001"
  timestamp: "2025-10-07T10:30:45"
  iteration_count: 3
  
  pending_messages: {
    "analyst_review": [
      FraudRiskAssessment {
        alert_id: "ALERT-001"
        overall_risk_score: 0.65
        recommended_action: "lock_account"
        ...
      }
    ]
  }
  
  shared_state: {
    "current_alert_id": "ALERT-001"
    "customer_id": 1
  }
  
  executor_states: {
    "usage_pattern_executor": {
      "analysis_complete": true
      "risk_score": 0.7
    }
    "location_analysis_executor": {
      "analysis_complete": true
      "risk_score": 0.85
    }
    "billing_charge_executor": {
      "analysis_complete": true
      "risk_score": 0.4
    }
    "fraud_risk_aggregator": {
      "assessment_complete": true
      "overall_risk": 0.65
    }
  }
}
```

## Error Handling Flow

```
┌─────────────────┐
│  Normal Flow    │
└────────┬────────┘
         ↓
    Try Execute
         ↓
    ┌────┴────┐
    │         │
Success    Exception
    │         │
    ↓         ↓
Continue  ┌──────────────┐
          │ Error Handler│
          └──────┬───────┘
                 ↓
          ┌─────────────┐
          │  Log Error  │
          └─────┬───────┘
                ↓
          ┌─────────────┐
          │  Checkpoint │
          │    Save     │
          └─────┬───────┘
                ↓
          ┌─────────────┐
          │   Notify    │
          │   Admin     │
          └─────┬───────┘
                ↓
          ┌─────────────┐
          │  Workflow   │
          │   FAILED    │
          └─────────────┘
```

---

## Legend

- `┌──┐` Executor/Component
- `↓` Message flow
- `→` Data flow
- `⏸️` Workflow paused
- `▶️` Workflow resumed
- `✅` Success/Complete
- `[...]` Parallel execution
- `{...}` Data structure
