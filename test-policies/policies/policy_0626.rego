package governance.monitoring.context.check.policy_0626

# Auto-generated policy 626 (Rego v1 syntax)
# Package: governance.monitoring.context.check

# Metadata
metadata := {
    "policy_id": "0626",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0626_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0626_allowed if {
    input.user.role == "admin"
}
