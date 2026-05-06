package risk.authorization.action.allow.logic.policy_0619

# Auto-generated policy 619 (Rego v1 syntax)
# Package: risk.authorization.action.allow.logic

# Metadata
metadata := {
    "policy_id": "0619",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0619_allowed if {
    input.user.active
    input.resource.public
}
policy_0619_allowed if {
    input.user.role == "admin"
}
default policy_0619_allowed = false
