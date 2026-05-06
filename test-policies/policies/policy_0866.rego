package risk.monitoring.action.verify.logic.policy_0866

# Auto-generated policy 866 (Rego v1 syntax)
# Package: risk.monitoring.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0866",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0866_allowed if {
    input.user.active
    input.resource.public
}
policy_0866_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0866_allowed = false
