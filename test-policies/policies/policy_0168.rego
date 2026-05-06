package access.authorization.user.validate.data.policy_0168

# Auto-generated policy 168 (Rego v1 syntax)
# Package: access.authorization.user.validate.data

# Metadata
metadata := {
    "policy_id": "0168",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0168_allowed if {
    input.user.active
    input.resource.public
}
policy_0168_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0168_allowed if {
    input.user.role == "admin"
}
