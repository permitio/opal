package security.enforcement.action.validate.policy_0573

# Auto-generated policy 573 (Rego v1 syntax)
# Package: security.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0573",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0573_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0573_allowed if {
    input.user.role == "admin"
}
policy_0573_allowed if {
    data.policies.security.enabled
}
policy_0573_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
