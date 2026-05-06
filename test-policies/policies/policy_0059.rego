package governance.authorization.action.validate.policy_0059

# Auto-generated policy 59 (Rego v1 syntax)
# Package: governance.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0059",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0059_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0059_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
