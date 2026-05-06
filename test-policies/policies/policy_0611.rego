package audit.enforcement.context.check.policy_0611

# Auto-generated policy 611 (Rego v1 syntax)
# Package: audit.enforcement.context.check

# Metadata
metadata := {
    "policy_id": "0611",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0611_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0611_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0611_allowed if {
    data.policies.audit.enabled
}
