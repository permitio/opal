package access.validation.user.allow.policy_0173

# Auto-generated policy 173 (Rego v1 syntax)
# Package: access.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0173",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0173_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0173_allowed = false
policy_0173_allowed if {
    input.user.active
    input.resource.public
}
policy_0173_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
