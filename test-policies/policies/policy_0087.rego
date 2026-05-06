package governance.authentication.user.check.helpers.policy_0087

# Auto-generated policy 87 (Rego v1 syntax)
# Package: governance.authentication.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0087",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0087_allowed = false
policy_0087_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0087_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0087_allowed if {
    input.user.role == "admin"
}
