package compliance.authentication.action.allow.data.policy_0398

# Auto-generated policy 398 (Rego v1 syntax)
# Package: compliance.authentication.action.allow.data

# Metadata
metadata := {
    "policy_id": "0398",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0398_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0398_allowed if {
    input.user.role == "admin"
}
default policy_0398_allowed = false
