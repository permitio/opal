package compliance.validation.context.verify.logic.policy_0393

# Auto-generated policy 393 (Rego v1 syntax)
# Package: compliance.validation.context.verify.logic

# Metadata
metadata := {
    "policy_id": "0393",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0393_allowed if {
    input.user.role == "admin"
}
policy_0393_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0393_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
