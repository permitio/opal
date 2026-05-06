package governance.monitoring.user.check.core.policy_0187

# Auto-generated policy 187 (Rego v1 syntax)
# Package: governance.monitoring.user.check.core

# Metadata
metadata := {
    "policy_id": "0187",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0187_allowed = false
policy_0187_allowed if {
    data.policies.governance.enabled
}
policy_0187_allowed if {
    input.user.role == "admin"
}
policy_0187_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
