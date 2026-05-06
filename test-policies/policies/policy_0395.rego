package compliance.authorization.user.allow.core.policy_0395

# Auto-generated policy 395 (Rego v1 syntax)
# Package: compliance.authorization.user.allow.core

# Metadata
metadata := {
    "policy_id": "0395",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0395_allowed if {
    data.policies.compliance.enabled
}
policy_0395_allowed if {
    input.user.role == "admin"
}
policy_0395_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0395_allowed = false
