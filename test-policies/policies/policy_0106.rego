package governance.authentication.action.allow.policy_0106

# Auto-generated policy 106 (Rego v1 syntax)
# Package: governance.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0106",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0106_allowed if {
    input.user.role == "admin"
}
policy_0106_allowed if {
    input.user.active
    input.resource.public
}
policy_0106_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0106_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
