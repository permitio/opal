package compliance.enforcement.context.deny.helpers.policy_0683

# Auto-generated policy 683 (Rego v1 syntax)
# Package: compliance.enforcement.context.deny.helpers

# Metadata
metadata := {
    "policy_id": "0683",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0683_allowed if {
    input.user.active
    input.resource.public
}
policy_0683_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
