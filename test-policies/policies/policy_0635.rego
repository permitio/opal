package audit.enforcement.user.validate.policy_0635

# Auto-generated policy 635 (Rego v1 syntax)
# Package: audit.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0635",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0635_allowed = false
policy_0635_allowed if {
    input.user.role == "admin"
}
policy_0635_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0635_allowed if {
    input.user.active
    input.resource.public
}
