package risk.authorization.action.check.data.policy_0783

# Auto-generated policy 783 (Rego v1 syntax)
# Package: risk.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0783",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0783_allowed if {
    input.user.active
    input.resource.public
}
policy_0783_allowed if {
    input.user.role == "admin"
}
