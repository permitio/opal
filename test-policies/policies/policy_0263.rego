package compliance.monitoring.action.verify.data.policy_0263

# Auto-generated policy 263 (Rego v1 syntax)
# Package: compliance.monitoring.action.verify.data

# Metadata
metadata := {
    "policy_id": "0263",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0263_allowed = false
policy_0263_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0263_allowed if {
    data.policies.compliance.enabled
}
policy_0263_allowed if {
    input.user.active
    input.resource.public
}
