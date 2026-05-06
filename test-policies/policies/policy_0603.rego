package audit.enforcement.user.check.helpers.policy_0603

# Auto-generated policy 603 (Rego v1 syntax)
# Package: audit.enforcement.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0603",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0603_allowed if {
    data.policies.audit.enabled
}
policy_0603_allowed if {
    input.user.active
    input.resource.public
}
policy_0603_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
