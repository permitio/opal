package audit.authorization.action.check.data.policy_0284

# Auto-generated policy 284 (Rego v1 syntax)
# Package: audit.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0284",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0284_allowed = false
policy_0284_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0284_allowed if {
    input.user.role == "admin"
}
