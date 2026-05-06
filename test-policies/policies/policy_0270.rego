package compliance.monitoring.policy.allow.data.policy_0270

# Auto-generated policy 270 (Rego v1 syntax)
# Package: compliance.monitoring.policy.allow.data

# Metadata
metadata := {
    "policy_id": "0270",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0270_allowed = false
policy_0270_allowed if {
    data.policies.compliance.enabled
}
policy_0270_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0270_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
