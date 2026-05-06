package audit.enforcement.context.check.policy_0348

# Auto-generated policy 348 (Rego v1 syntax)
# Package: audit.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0348",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0348_allowed if {
    input.user.role == "admin"
}
policy_0348_allowed if {
    input.user.active
    input.resource.public
}
policy_0348_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
