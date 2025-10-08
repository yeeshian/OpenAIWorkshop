
## **Contoso Fraud Detection & Escalation Workflow**  
  
**Business Context:**    
Contoso’s automated systems flag suspicious account activity, but certain cases require a fraud analyst to review before taking action (e.g., locking account, reversing charges).  
  
**Flow:**  
1. **Event Trigger:** Backend monitoring system sends “Suspicious Activity Alert” (login from multiple countries, large data usage spike).  
2. **AlertRouterExecutor** → routes alert to multiple analysis executors:  
   - `UsagePatternExecutor` → checks recent usage against historical baseline.  
   - `LocationAnalysisExecutor` → checks geolocation anomalies.  
   - `BillingChargeExecutor` → checks for unusual purchases or charges.  
3. **Fan-In** to `FraudRiskAggregatorExecutor`:  
   - Produces `FraudRiskScore` and recommended action (lock account, refund charges, ignore).  
4. **SwitchCaseEdgeRunner**:  
   - If risk score ≥ threshold → route to `RequestInfoExecutor` for human fraud analyst review.  
   - Else → route to `AutoClearExecutor`.  
5. **RequestInfoExecutor** → sends “Fraud Case Review Request” to analyst with full context.  
6. **Workflow pauses** — checkpoint saved.  
7. **Analyst decides** (approve lock/refund or clear).  
8. Workflow resumes:  
   - `FraudActionExecutor` → performs chosen action (e.g., lock account, reverse charges).  
9. **FinalNotificationExecutor** → informs customer and logs audit trail.  
  
**Highlight:**    
- Demonstrates **event-driven workflow** triggered by backend system.  
- Multiple data sources fan-out and aggregate to produce a single risk assessment.  
- Human analyst gating ensures **false positives** don’t harm legitimate customers.  
- **Checkpointing** means the workflow can pause indefinitely until analyst responds.  
