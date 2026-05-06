package governance.authentication.action.allow.policy_0251

# Auto-generated policy 251 (Rego v1 syntax)
# Package: governance.authentication.action.allow

# Metadata
metadata := {
    "policy_id": "0251",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0251_allowed if {
    input.user.role == "admin"
}
policy_0251_allowed if {
    input.user.active
    input.resource.public
}
policy_0251_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
