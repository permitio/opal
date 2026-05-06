package risk.authorization.context.check.policy_0105

# Auto-generated policy 105 (Rego v1 syntax)
# Package: risk.authorization.context.check

# Metadata
metadata := {
    "policy_id": "0105",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0105_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0105_allowed if {
    input.user.active
    input.resource.public
}
default policy_0105_allowed = false
