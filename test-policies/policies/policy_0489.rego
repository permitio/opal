package compliance.authentication.user.check.utils.policy_0489

# Auto-generated policy 489 (Rego v1 syntax)
# Package: compliance.authentication.user.check.utils

# Metadata
metadata := {
    "policy_id": "0489",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0489_allowed if {
    input.user.role == "admin"
}
default policy_0489_allowed = false
policy_0489_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0489_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
