package risk.authorization.user.validate.utils.policy_0148

# Auto-generated policy 148 (Rego v1 syntax)
# Package: risk.authorization.user.validate.utils

# Metadata
metadata := {
    "policy_id": "0148",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0148_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0148_allowed if {
    input.user.role == "admin"
}
policy_0148_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0148_allowed if {
    input.user.active
    input.resource.public
}
